"""Control API – Kubernetes cluster + secret management endpoints."""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import write_audit
from app.core.crypto import decrypt_key, encrypt_key
from app.config import get_settings
from app.database import get_db
from app.models import (
    ExternalCertificate,
    KubernetesCluster,
    KubernetesClusterConnectionStatus,
    KubernetesSecretAssignment,
    KubernetesSecretDryRun,
    KubernetesSecretDryRunAction,
    KubernetesSecretDryRunStatus,
    KubernetesSecretHealthStatus,
    KubernetesSecretLifecycleStatus,
    KubernetesSecretOperation,
    KubernetesSecretOperationAction,
    KubernetesSecretOperationStatus,
)
from app.schemas import (
    KubernetesClusterCreate,
    KubernetesClusterCredentialsUpdate,
    KubernetesClusterRead,
    KubernetesClusterTestConnectionResponse,
    KubernetesDryRunConfirmRequest,
    KubernetesDryRunRead,
    KubernetesSecretAssignmentCreate,
    KubernetesSecretAssignmentRead,
    KubernetesSecretOperationRead,
    PaginatedResponse,
)
from app.services.kubernetes_secrets import (
    KubernetesApiClient,
    KubernetesApiError,
    build_adopt_patch,
    build_secret_merge_patch,
    build_tls_secret_body,
    decode_snapshot,
    encode_snapshot,
    extract_secret_resource_version,
    extract_secret_serial,
    is_platform_managed,
    parse_service_account_kubeconfig,
    summarize_tls_diff,
    verify_certificate_key_pair,
)

from app.api.control._helpers import _actor, _ip

router = APIRouter()


# ===========================================================================
# Helpers (kubernetes-specific)
# ===========================================================================


def _assignment_read(
    assignment: KubernetesSecretAssignment,
    cluster: KubernetesCluster,
    ext_cert: ExternalCertificate,
) -> dict:
    data = assignment.__dict__.copy()
    data.pop("_sa_instance_state", None)
    data["cluster_name"] = cluster.name
    data["external_cert_subject_cn"] = ext_cert.subject_cn
    return data


async def _load_k8s_assignment(
    db: AsyncSession, assignment_id: uuid.UUID
) -> tuple[KubernetesSecretAssignment, KubernetesCluster, ExternalCertificate]:
    result = await db.execute(
        select(KubernetesSecretAssignment)
        .where(
            KubernetesSecretAssignment.id == assignment_id,
            KubernetesSecretAssignment.is_active.is_(True),
        )
        .options(
            selectinload(KubernetesSecretAssignment.cluster),
            selectinload(KubernetesSecretAssignment.external_cert),
        )
    )
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Kubernetes Secret assignment not found")
    return assignment, assignment.cluster, assignment.external_cert


def _decrypt_external_cert_key(ext_cert: ExternalCertificate) -> str:
    return decrypt_key(
        ext_cert.key_pem_encrypted,
        get_settings().ca_key_encryption_key,
    ).decode()


def _kubernetes_client_from_cluster(cluster: KubernetesCluster) -> KubernetesApiClient:
    kubeconfig_text = decrypt_key(
        cluster.kubeconfig_encrypted,
        get_settings().ca_key_encryption_key,
    ).decode()
    parsed = parse_service_account_kubeconfig(kubeconfig_text)
    return KubernetesApiClient(parsed)


async def _load_pending_dry_run(
    db: AsyncSession,
    dry_run_id: uuid.UUID,
    assignment_id: uuid.UUID,
    action: KubernetesSecretDryRunAction,
) -> KubernetesSecretDryRun:
    dry_run = await db.get(KubernetesSecretDryRun, dry_run_id)
    if not dry_run or dry_run.assignment_id != assignment_id or dry_run.action != action:
        raise HTTPException(status_code=404, detail="Dry-run not found")
    if dry_run.status != KubernetesSecretDryRunStatus.PENDING:
        raise HTTPException(status_code=409, detail=f"Dry-run is already {dry_run.status.value}")
    if _ensure_aware(dry_run.expires_at) <= datetime.now(timezone.utc):
        dry_run.status = KubernetesSecretDryRunStatus.EXPIRED
        db.add(dry_run)
        await db.commit()
        raise HTTPException(status_code=409, detail="Dry-run expired")
    return dry_run


def _new_k8s_operation(
    *,
    assignment: KubernetesSecretAssignment,
    action: KubernetesSecretOperationAction,
    dry_run: KubernetesSecretDryRun | None,
    actor: str,
) -> KubernetesSecretOperation:
    return KubernetesSecretOperation(
        cluster_id=assignment.cluster_id,
        assignment_id=assignment.id,
        action=action,
        status=KubernetesSecretOperationStatus.RUNNING,
        dry_run_id=dry_run.id if dry_run else None,
        external_cert_id=assignment.external_cert_id,
        created_by=actor,
    )


async def _apply_k8s_assignment_validation(
    db: AsyncSession,
    *,
    assignment: KubernetesSecretAssignment,
    cluster: KubernetesCluster,
    ext_cert: ExternalCertificate,
    actor: str,
    ip_address: str | None,
) -> KubernetesSecretOperation:
    operation = _new_k8s_operation(
        assignment=assignment,
        action=KubernetesSecretOperationAction.VALIDATE,
        dry_run=None,
        actor=actor,
    )
    db.add(operation)
    await db.flush()

    try:
        secret = await _kubernetes_client_from_cluster(cluster).get_secret(
            assignment.namespace, assignment.secret_name
        )
        assignment.last_validated_at = datetime.now(timezone.utc)
        if not secret:
            assignment.health_status = KubernetesSecretHealthStatus.MISSING
        elif not is_platform_managed(secret, str(assignment.id)):
            assignment.health_status = KubernetesSecretHealthStatus.UNMANAGED
        else:
            try:
                serial = extract_secret_serial(secret)
                assignment.current_serial_hex = serial
                assignment.current_resource_version = extract_secret_resource_version(secret)
                assignment.health_status = (
                    KubernetesSecretHealthStatus.HEALTHY
                    if serial == ext_cert.serial_hex
                    else KubernetesSecretHealthStatus.SERIAL_MISMATCH
                )
            except Exception:
                assignment.health_status = KubernetesSecretHealthStatus.INVALID_SECRET

        operation.status = KubernetesSecretOperationStatus.SUCCEEDED
        operation.serial_after = assignment.current_serial_hex
        operation.resource_version_after = assignment.current_resource_version
        operation.finished_at = datetime.now(timezone.utc)
        db.add_all([assignment, operation])
        await write_audit(
            db,
            action="kubernetes_secret_validated",
            entity_type="kubernetes_secret_assignment",
            entity_id=assignment.id,
            actor=actor,
            details={"health_status": assignment.health_status.value},
            ip_address=ip_address,
        )
        return operation
    except KubernetesApiError as e:
        assignment.last_validated_at = datetime.now(timezone.utc)
        assignment.health_status = (
            KubernetesSecretHealthStatus.RBAC_ERROR
            if e.status_code == 403
            else KubernetesSecretHealthStatus.CLUSTER_UNREACHABLE
        )
        operation.status = KubernetesSecretOperationStatus.FAILED
        operation.error_code = e.__class__.__name__
        operation.error_message = str(e)
        operation.finished_at = datetime.now(timezone.utc)
        db.add_all([assignment, operation])
        raise
    except Exception as e:
        assignment.last_validated_at = datetime.now(timezone.utc)
        assignment.health_status = KubernetesSecretHealthStatus.CLUSTER_UNREACHABLE
        operation.status = KubernetesSecretOperationStatus.FAILED
        operation.error_code = e.__class__.__name__
        operation.error_message = str(e)
        operation.finished_at = datetime.now(timezone.utc)
        db.add_all([assignment, operation])
        raise


async def _mark_k8s_operation_failed(
    db: AsyncSession,
    operation: KubernetesSecretOperation,
    assignment: KubernetesSecretAssignment,
    message: str,
) -> None:
    operation.status = KubernetesSecretOperationStatus.FAILED
    operation.error_code = "kubernetes_secret_operation_failed"
    operation.error_message = message
    operation.finished_at = datetime.now(timezone.utc)
    assignment.lifecycle_status = KubernetesSecretLifecycleStatus.FAILED
    db.add_all([operation, assignment])
    await db.commit()


def _http_status_from_k8s(error: KubernetesApiError) -> int:
    if error.status_code == 403:
        return 403
    if error.status_code == 404:
        return 404
    if error.status_code == 409:
        return 409
    return 502


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


# ===========================================================================
# Endpoints
# ===========================================================================


@router.post(
    "/kubernetes/clusters",
    response_model=KubernetesClusterRead,
    status_code=status.HTTP_201_CREATED,
    tags=["control / kubernetes"],
    summary="上传 Kubernetes ServiceAccount kubeconfig",
)
async def create_kubernetes_cluster(
    body: KubernetesClusterCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    try:
        parsed = parse_service_account_kubeconfig(body.kubeconfig)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    cluster = KubernetesCluster(
        name=body.name,
        environment=body.environment,
        api_server=parsed.api_server,
        default_namespace=body.default_namespace or parsed.default_namespace,
        kubeconfig_encrypted=encrypt_key(
            body.kubeconfig.encode(), settings.ca_key_encryption_key
        ),
    )
    db.add(cluster)
    await db.flush()

    await write_audit(
        db,
        action="kubernetes_cluster_created",
        entity_type="kubernetes_cluster",
        entity_id=cluster.id,
        actor=_actor(request),
        details={
            "name": cluster.name,
            "environment": cluster.environment,
            "api_server": cluster.api_server,
            "default_namespace": cluster.default_namespace,
        },
        ip_address=_ip(request),
    )
    await db.commit()
    await db.refresh(cluster)
    return cluster


@router.get(
    "/kubernetes/clusters",
    response_model=PaginatedResponse[KubernetesClusterRead],
    tags=["control / kubernetes"],
    summary="Kubernetes 集群列表",
)
async def list_kubernetes_clusters(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    base = select(KubernetesCluster)
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    result = await db.execute(
        base.order_by(KubernetesCluster.created_at.desc()).offset(skip).limit(limit)
    )
    return PaginatedResponse(items=list(result.scalars().all()), total=total, skip=skip, limit=limit)


@router.post(
    "/kubernetes/clusters/{cluster_id}/test-connection",
    response_model=KubernetesClusterTestConnectionResponse,
    tags=["control / kubernetes"],
    summary="只读测试 Kubernetes 连接",
)
async def test_kubernetes_cluster_connection(
    cluster_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    cluster = await db.get(KubernetesCluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Kubernetes cluster not found")

    operation = KubernetesSecretOperation(
        cluster_id=cluster.id,
        assignment_id=None,
        action=KubernetesSecretOperationAction.TEST_CONNECTION,
        status=KubernetesSecretOperationStatus.RUNNING,
        created_by=_actor(request),
    )
    db.add(operation)
    await db.flush()

    try:
        client = _kubernetes_client_from_cluster(cluster)
        version_payload = await client.get_version()
        if cluster.default_namespace:
            await client.get_namespace(cluster.default_namespace)
        version = version_payload.get("gitVersion")
        cluster.connection_status = KubernetesClusterConnectionStatus.ACTIVE
        cluster.last_checked_at = datetime.now(timezone.utc)
        operation.status = KubernetesSecretOperationStatus.SUCCEEDED
        operation.finished_at = datetime.now(timezone.utc)
        db.add_all([cluster, operation])
        await write_audit(
            db,
            action="kubernetes_cluster_connection_tested",
            entity_type="kubernetes_cluster",
            entity_id=cluster.id,
            actor=_actor(request),
            details={"status": "active", "version": version},
            ip_address=_ip(request),
        )
        await db.commit()
        return KubernetesClusterTestConnectionResponse(
            cluster_id=cluster.id,
            status=cluster.connection_status,
            version=version,
            default_namespace=cluster.default_namespace,
            message="Kubernetes API reachable",
        )
    except Exception as e:
        cluster.connection_status = KubernetesClusterConnectionStatus.FAILED
        cluster.last_checked_at = datetime.now(timezone.utc)
        operation.status = KubernetesSecretOperationStatus.FAILED
        operation.error_code = e.__class__.__name__
        operation.error_message = str(e)
        operation.finished_at = datetime.now(timezone.utc)
        db.add_all([cluster, operation])
        await db.commit()
        raise HTTPException(status_code=502, detail=f"Kubernetes connection failed: {e}") from e


@router.put(
    "/kubernetes/clusters/{cluster_id}/credentials",
    response_model=KubernetesClusterRead,
    tags=["control / kubernetes"],
    summary="更新 Kubernetes ServiceAccount kubeconfig",
)
async def update_kubernetes_cluster_credentials(
    cluster_id: uuid.UUID,
    body: KubernetesClusterCredentialsUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    cluster = await db.get(KubernetesCluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Kubernetes cluster not found")

    try:
        parsed = parse_service_account_kubeconfig(body.kubeconfig)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    cluster.api_server = parsed.api_server
    cluster.default_namespace = body.default_namespace or parsed.default_namespace
    cluster.kubeconfig_encrypted = encrypt_key(
        body.kubeconfig.encode(), settings.ca_key_encryption_key
    )
    cluster.connection_status = KubernetesClusterConnectionStatus.UNKNOWN
    db.add(cluster)
    await db.flush()

    assignments_result = await db.execute(
        select(KubernetesSecretAssignment)
        .where(
            KubernetesSecretAssignment.cluster_id == cluster.id,
            KubernetesSecretAssignment.is_active.is_(True),
        )
        .options(selectinload(KubernetesSecretAssignment.external_cert))
    )
    assignments = list(assignments_result.scalars().all())
    validation_failures = 0
    for assignment in assignments:
        try:
            await _apply_k8s_assignment_validation(
                db,
                assignment=assignment,
                cluster=cluster,
                ext_cert=assignment.external_cert,
                actor=_actor(request),
                ip_address=_ip(request),
            )
        except Exception:
            validation_failures += 1

    await write_audit(
        db,
        action="kubernetes_cluster_credentials_updated",
        entity_type="kubernetes_cluster",
        entity_id=cluster.id,
        actor=_actor(request),
        details={
            "api_server": cluster.api_server,
            "validated_assignments": len(assignments) - validation_failures,
            "validation_failures": validation_failures,
        },
        ip_address=_ip(request),
    )
    await db.commit()
    await db.refresh(cluster)
    return cluster


@router.post(
    "/kubernetes/assignments",
    response_model=KubernetesSecretAssignmentRead,
    status_code=status.HTTP_201_CREATED,
    tags=["control / kubernetes"],
    summary="创建 Kubernetes Secret 证书分配",
)
async def create_kubernetes_secret_assignment(
    body: KubernetesSecretAssignmentCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    cluster = await db.get(KubernetesCluster, body.cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Kubernetes cluster not found")
    ext_cert = await db.get(ExternalCertificate, body.external_cert_id)
    if not ext_cert:
        raise HTTPException(status_code=404, detail="External certificate not found")

    existing_result = await db.execute(
        select(KubernetesSecretAssignment).where(
            KubernetesSecretAssignment.cluster_id == body.cluster_id,
            KubernetesSecretAssignment.namespace == body.namespace,
            KubernetesSecretAssignment.secret_name == body.secret_name,
            KubernetesSecretAssignment.is_active.is_(True),
        )
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="An active assignment already exists for this cluster/namespace/secretName",
        )

    assignment = KubernetesSecretAssignment(
        cluster_id=body.cluster_id,
        external_cert_id=body.external_cert_id,
        namespace=body.namespace,
        secret_name=body.secret_name,
        auto_track_latest=body.auto_track_latest,
        auto_deploy=body.auto_deploy,
    )
    db.add(assignment)
    await db.flush()

    await write_audit(
        db,
        action="kubernetes_secret_assignment_created",
        entity_type="kubernetes_secret_assignment",
        entity_id=assignment.id,
        actor=_actor(request),
        details={
            "cluster": cluster.name,
            "namespace": body.namespace,
            "secret_name": body.secret_name,
            "external_cert_id": str(body.external_cert_id),
        },
        ip_address=_ip(request),
    )
    await db.commit()
    await db.refresh(assignment)
    return _assignment_read(assignment, cluster, ext_cert)


@router.get(
    "/kubernetes/assignments",
    response_model=PaginatedResponse[KubernetesSecretAssignmentRead],
    tags=["control / kubernetes"],
    summary="Kubernetes Secret 分配列表",
)
async def list_kubernetes_secret_assignments(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    base = select(KubernetesSecretAssignment).where(
        KubernetesSecretAssignment.is_active.is_(True)
    )
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    result = await db.execute(
        base.options(
            selectinload(KubernetesSecretAssignment.cluster),
            selectinload(KubernetesSecretAssignment.external_cert),
        )
        .order_by(KubernetesSecretAssignment.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    items = [
        _assignment_read(item, item.cluster, item.external_cert)
        for item in result.scalars().all()
    ]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@router.delete(
    "/kubernetes/assignments/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["control / kubernetes"],
    summary="删除平台侧 Kubernetes Secret 分配",
)
async def delete_kubernetes_secret_assignment(
    assignment_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    assignment = await db.get(KubernetesSecretAssignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Kubernetes Secret assignment not found")
    assignment.is_active = False
    db.add(assignment)
    await write_audit(
        db,
        action="kubernetes_secret_assignment_deleted",
        entity_type="kubernetes_secret_assignment",
        entity_id=assignment.id,
        actor=_actor(request),
        details={"cluster_id": str(assignment.cluster_id), "secret_name": assignment.secret_name},
        ip_address=_ip(request),
    )
    await db.commit()


@router.post(
    "/kubernetes/assignments/{assignment_id}/deploy/dry-run",
    response_model=KubernetesDryRunRead,
    status_code=status.HTTP_201_CREATED,
    tags=["control / kubernetes"],
    summary="生成 Kubernetes Secret deploy dry-run",
)
async def dry_run_kubernetes_secret_deploy(
    assignment_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    assignment, cluster, ext_cert = await _load_k8s_assignment(db, assignment_id)
    key_pem = _decrypt_external_cert_key(ext_cert)
    try:
        verify_certificate_key_pair(ext_cert.cert_pem, key_pem)
        current_secret = await _kubernetes_client_from_cluster(cluster).get_secret(
            assignment.namespace, assignment.secret_name
        )
    except KubernetesApiError as e:
        raise HTTPException(status_code=_http_status_from_k8s(e), detail=str(e)) from e

    if current_secret and not is_platform_managed(current_secret, str(assignment.id)):
        raise HTTPException(
            status_code=409,
            detail="Existing Secret is not managed by this assignment. Adopt it first.",
        )

    resource_version = extract_secret_resource_version(current_secret)
    dry_run = KubernetesSecretDryRun(
        cluster_id=cluster.id,
        assignment_id=assignment.id,
        action=KubernetesSecretDryRunAction.DEPLOY,
        external_cert_id=ext_cert.id,
        namespace=assignment.namespace,
        secret_name=assignment.secret_name,
        current_resource_version=resource_version,
        diff=summarize_tls_diff(
            current_secret=current_secret,
            target_serial_hex=ext_cert.serial_hex,
            target_resource_version=resource_version,
        ),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        created_by=_actor(request),
    )
    db.add(dry_run)
    await db.flush()
    await write_audit(
        db,
        action="kubernetes_secret_dry_run_created",
        entity_type="kubernetes_secret_dry_run",
        entity_id=dry_run.id,
        actor=_actor(request),
        details={"assignment_id": str(assignment.id), "action": "deploy"},
        ip_address=_ip(request),
    )
    await db.commit()
    await db.refresh(dry_run)
    return dry_run


@router.post(
    "/kubernetes/assignments/{assignment_id}/deploy/confirm",
    response_model=KubernetesSecretAssignmentRead,
    tags=["control / kubernetes"],
    summary="确认 Kubernetes Secret deploy dry-run 并写入集群",
)
async def confirm_kubernetes_secret_deploy(
    assignment_id: uuid.UUID,
    body: KubernetesDryRunConfirmRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    assignment, cluster, ext_cert = await _load_k8s_assignment(db, assignment_id)
    dry_run = await _load_pending_dry_run(
        db, body.dry_run_id, assignment.id, KubernetesSecretDryRunAction.DEPLOY
    )
    operation = _new_k8s_operation(
        assignment=assignment,
        action=KubernetesSecretOperationAction.DEPLOY,
        dry_run=dry_run,
        actor=_actor(request),
    )
    db.add(operation)
    await db.flush()

    try:
        client = _kubernetes_client_from_cluster(cluster)
        key_pem = _decrypt_external_cert_key(ext_cert)
        verify_certificate_key_pair(ext_cert.cert_pem, key_pem)
        current_secret = await client.get_secret(assignment.namespace, assignment.secret_name)
        current_resource_version = extract_secret_resource_version(current_secret)
        if current_resource_version != dry_run.current_resource_version:
            raise HTTPException(status_code=409, detail="Secret resourceVersion changed; rerun dry-run")

        operation.resource_version_before = current_resource_version
        operation.serial_before = extract_secret_serial(current_secret) if current_secret else None
        operation.diff = dry_run.diff

        if current_secret:
            assignment.last_snapshot_encrypted = encrypt_key(
                encode_snapshot(current_secret), get_settings().ca_key_encryption_key
            )
            assignment.last_snapshot_serial_hex = operation.serial_before
            written = await client.patch_secret(
                assignment.namespace,
                assignment.secret_name,
                build_secret_merge_patch(
                    cert_pem=ext_cert.cert_pem,
                    key_pem=key_pem,
                    chain_pem=ext_cert.chain_pem,
                    assignment_id=str(assignment.id),
                    external_cert_id=str(ext_cert.id),
                    serial_hex=ext_cert.serial_hex,
                ),
            )
        else:
            written = await client.create_secret(
                assignment.namespace,
                build_tls_secret_body(
                    namespace=assignment.namespace,
                    secret_name=assignment.secret_name,
                    cert_pem=ext_cert.cert_pem,
                    key_pem=key_pem,
                    chain_pem=ext_cert.chain_pem,
                    assignment_id=str(assignment.id),
                    external_cert_id=str(ext_cert.id),
                    serial_hex=ext_cert.serial_hex,
                ),
            )

        verified = await client.get_secret(assignment.namespace, assignment.secret_name)
        serial_after = extract_secret_serial(verified or written)
        if serial_after != ext_cert.serial_hex:
            raise HTTPException(status_code=409, detail="Read-back certificate serial mismatch")

        operation.resource_version_after = extract_secret_resource_version(verified or written)
        operation.serial_after = serial_after
        operation.status = KubernetesSecretOperationStatus.SUCCEEDED
        operation.finished_at = datetime.now(timezone.utc)
        dry_run.status = KubernetesSecretDryRunStatus.CONFIRMED
        assignment.lifecycle_status = KubernetesSecretLifecycleStatus.DEPLOYED
        assignment.health_status = KubernetesSecretHealthStatus.HEALTHY
        assignment.current_resource_version = operation.resource_version_after
        assignment.current_serial_hex = serial_after
        assignment.last_deployed_at = datetime.now(timezone.utc)
        db.add_all([assignment, dry_run, operation])
        await write_audit(
            db,
            action="kubernetes_secret_deployed",
            entity_type="kubernetes_secret_assignment",
            entity_id=assignment.id,
            actor=_actor(request),
            details={"operation_id": str(operation.id), "serial": serial_after},
            ip_address=_ip(request),
        )
        await db.commit()
        await db.refresh(assignment)
        return _assignment_read(assignment, cluster, ext_cert)
    except HTTPException as e:
        await _mark_k8s_operation_failed(db, operation, assignment, e.detail)
        raise
    except Exception as e:
        await _mark_k8s_operation_failed(db, operation, assignment, str(e))
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post(
    "/kubernetes/assignments/{assignment_id}/adopt/dry-run",
    response_model=KubernetesDryRunRead,
    status_code=status.HTTP_201_CREATED,
    tags=["control / kubernetes"],
    summary="生成 Kubernetes Secret adopt dry-run",
)
async def dry_run_kubernetes_secret_adopt(
    assignment_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    assignment, cluster, _ext_cert = await _load_k8s_assignment(db, assignment_id)
    secret = await _kubernetes_client_from_cluster(cluster).get_secret(
        assignment.namespace, assignment.secret_name
    )
    if not secret:
        raise HTTPException(status_code=404, detail="Secret does not exist; deploy can create it")
    resource_version = extract_secret_resource_version(secret)
    try:
        current_serial = extract_secret_serial(secret)
        health = KubernetesSecretHealthStatus.HEALTHY
    except Exception:
        current_serial = None
        health = KubernetesSecretHealthStatus.INVALID_SECRET
    dry_run = KubernetesSecretDryRun(
        cluster_id=cluster.id,
        assignment_id=assignment.id,
        action=KubernetesSecretDryRunAction.ADOPT,
        external_cert_id=assignment.external_cert_id,
        namespace=assignment.namespace,
        secret_name=assignment.secret_name,
        current_resource_version=resource_version,
        diff=[
            {"path": "metadata.annotations.cert-control-plane.io/managed", "before": None, "after": "true"},
            {"path": "data.tls.crt", "before": current_serial or "unparseable", "after": "unchanged"},
        ],
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        created_by=_actor(request),
    )
    assignment.health_status = health
    db.add_all([assignment, dry_run])
    await db.flush()
    await write_audit(
        db,
        action="kubernetes_secret_dry_run_created",
        entity_type="kubernetes_secret_dry_run",
        entity_id=dry_run.id,
        actor=_actor(request),
        details={"assignment_id": str(assignment.id), "action": "adopt"},
        ip_address=_ip(request),
    )
    await db.commit()
    await db.refresh(dry_run)
    return dry_run


@router.post(
    "/kubernetes/assignments/{assignment_id}/adopt/confirm",
    response_model=KubernetesSecretAssignmentRead,
    tags=["control / kubernetes"],
    summary="确认 Kubernetes Secret adopt dry-run",
)
async def confirm_kubernetes_secret_adopt(
    assignment_id: uuid.UUID,
    body: KubernetesDryRunConfirmRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    assignment, cluster, ext_cert = await _load_k8s_assignment(db, assignment_id)
    dry_run = await _load_pending_dry_run(
        db, body.dry_run_id, assignment.id, KubernetesSecretDryRunAction.ADOPT
    )
    operation = _new_k8s_operation(
        assignment=assignment,
        action=KubernetesSecretOperationAction.ADOPT,
        dry_run=dry_run,
        actor=_actor(request),
    )
    db.add(operation)
    await db.flush()
    try:
        client = _kubernetes_client_from_cluster(cluster)
        secret = await client.get_secret(assignment.namespace, assignment.secret_name)
        if not secret:
            raise HTTPException(status_code=404, detail="Secret not found")
        if extract_secret_resource_version(secret) != dry_run.current_resource_version:
            raise HTTPException(status_code=409, detail="Secret resourceVersion changed; rerun dry-run")
        current_serial = extract_secret_serial(secret)
        written = await client.patch_secret(
            assignment.namespace,
            assignment.secret_name,
            build_adopt_patch(assignment_id=str(assignment.id), current_serial_hex=current_serial),
        )
        dry_run.status = KubernetesSecretDryRunStatus.CONFIRMED
        assignment.lifecycle_status = KubernetesSecretLifecycleStatus.ADOPTED
        assignment.health_status = KubernetesSecretHealthStatus.HEALTHY
        assignment.current_resource_version = extract_secret_resource_version(written)
        assignment.current_serial_hex = current_serial
        operation.status = KubernetesSecretOperationStatus.SUCCEEDED
        operation.resource_version_before = dry_run.current_resource_version
        operation.resource_version_after = assignment.current_resource_version
        operation.serial_before = current_serial
        operation.serial_after = current_serial
        operation.finished_at = datetime.now(timezone.utc)
        db.add_all([assignment, dry_run, operation])
        await write_audit(
            db,
            action="kubernetes_secret_adopted",
            entity_type="kubernetes_secret_assignment",
            entity_id=assignment.id,
            actor=_actor(request),
            details={"operation_id": str(operation.id), "serial": current_serial},
            ip_address=_ip(request),
        )
        await db.commit()
        await db.refresh(assignment)
        return _assignment_read(assignment, cluster, ext_cert)
    except HTTPException as e:
        await _mark_k8s_operation_failed(db, operation, assignment, e.detail)
        raise
    except Exception as e:
        await _mark_k8s_operation_failed(db, operation, assignment, str(e))
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post(
    "/kubernetes/assignments/{assignment_id}/rollback/dry-run",
    response_model=KubernetesDryRunRead,
    status_code=status.HTTP_201_CREATED,
    tags=["control / kubernetes"],
    summary="生成 Kubernetes Secret 最近一次回滚 dry-run",
)
async def dry_run_kubernetes_secret_rollback(
    assignment_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    assignment, cluster, _ext_cert = await _load_k8s_assignment(db, assignment_id)
    if not assignment.last_snapshot_encrypted:
        raise HTTPException(status_code=409, detail="No previous successful deployment snapshot")
    secret = await _kubernetes_client_from_cluster(cluster).get_secret(
        assignment.namespace, assignment.secret_name
    )
    resource_version = extract_secret_resource_version(secret)
    dry_run = KubernetesSecretDryRun(
        cluster_id=cluster.id,
        assignment_id=assignment.id,
        action=KubernetesSecretDryRunAction.ROLLBACK,
        external_cert_id=assignment.external_cert_id,
        namespace=assignment.namespace,
        secret_name=assignment.secret_name,
        current_resource_version=resource_version,
        diff=[
            {
                "path": "data.tls.crt",
                "before": assignment.current_serial_hex,
                "after": assignment.last_snapshot_serial_hex,
            }
        ],
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        created_by=_actor(request),
    )
    db.add(dry_run)
    await db.flush()
    await write_audit(
        db,
        action="kubernetes_secret_dry_run_created",
        entity_type="kubernetes_secret_dry_run",
        entity_id=dry_run.id,
        actor=_actor(request),
        details={"assignment_id": str(assignment.id), "action": "rollback"},
        ip_address=_ip(request),
    )
    await db.commit()
    await db.refresh(dry_run)
    return dry_run


@router.post(
    "/kubernetes/assignments/{assignment_id}/rollback/confirm",
    response_model=KubernetesSecretAssignmentRead,
    tags=["control / kubernetes"],
    summary="确认 Kubernetes Secret 最近一次回滚",
)
async def confirm_kubernetes_secret_rollback(
    assignment_id: uuid.UUID,
    body: KubernetesDryRunConfirmRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    assignment, cluster, ext_cert = await _load_k8s_assignment(db, assignment_id)
    dry_run = await _load_pending_dry_run(
        db, body.dry_run_id, assignment.id, KubernetesSecretDryRunAction.ROLLBACK
    )
    if not assignment.last_snapshot_encrypted:
        raise HTTPException(status_code=409, detail="No previous successful deployment snapshot")
    operation = _new_k8s_operation(
        assignment=assignment,
        action=KubernetesSecretOperationAction.ROLLBACK,
        dry_run=dry_run,
        actor=_actor(request),
    )
    db.add(operation)
    await db.flush()
    try:
        client = _kubernetes_client_from_cluster(cluster)
        current_secret = await client.get_secret(assignment.namespace, assignment.secret_name)
        serial_before = assignment.current_serial_hex
        if extract_secret_resource_version(current_secret) != dry_run.current_resource_version:
            raise HTTPException(status_code=409, detail="Secret resourceVersion changed; rerun dry-run")
        snapshot = decode_snapshot(
            decrypt_key(assignment.last_snapshot_encrypted, get_settings().ca_key_encryption_key)
        )
        snapshot_data = snapshot.get("data") or {}
        patch = {
            "data": {
                "tls.crt": snapshot_data["tls.crt"],
                "tls.key": snapshot_data["tls.key"],
            },
            "metadata": {
                "annotations": {
                    "cert-control-plane.io/managed": "true",
                    "cert-control-plane.io/assignment-id": str(assignment.id),
                    "cert-control-plane.io/serial": assignment.last_snapshot_serial_hex or "",
                    "cert-control-plane.io/rolled-back-at": datetime.now(timezone.utc).isoformat(),
                    "cert-control-plane.io/operation-id": str(operation.id),
                }
            },
        }
        written = await client.patch_secret(assignment.namespace, assignment.secret_name, patch)
        verified = await client.get_secret(assignment.namespace, assignment.secret_name)
        serial_after = extract_secret_serial(verified or written)
        dry_run.status = KubernetesSecretDryRunStatus.CONFIRMED
        assignment.lifecycle_status = KubernetesSecretLifecycleStatus.ROLLED_BACK
        assignment.health_status = KubernetesSecretHealthStatus.HEALTHY
        assignment.current_resource_version = extract_secret_resource_version(verified or written)
        assignment.current_serial_hex = serial_after
        operation.status = KubernetesSecretOperationStatus.SUCCEEDED
        operation.resource_version_before = dry_run.current_resource_version
        operation.resource_version_after = assignment.current_resource_version
        operation.serial_before = serial_before
        operation.serial_after = serial_after
        operation.finished_at = datetime.now(timezone.utc)
        db.add_all([assignment, dry_run, operation])
        await write_audit(
            db,
            action="kubernetes_secret_rolled_back",
            entity_type="kubernetes_secret_assignment",
            entity_id=assignment.id,
            actor=_actor(request),
            details={"operation_id": str(operation.id), "serial": serial_after},
            ip_address=_ip(request),
        )
        await db.commit()
        await db.refresh(assignment)
        return _assignment_read(assignment, cluster, ext_cert)
    except HTTPException as e:
        await _mark_k8s_operation_failed(db, operation, assignment, e.detail)
        raise
    except Exception as e:
        await _mark_k8s_operation_failed(db, operation, assignment, str(e))
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post(
    "/kubernetes/assignments/{assignment_id}/validate",
    response_model=KubernetesSecretAssignmentRead,
    tags=["control / kubernetes"],
    summary="只读校验 Kubernetes Secret 状态",
)
async def validate_kubernetes_secret_assignment(
    assignment_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    assignment, cluster, ext_cert = await _load_k8s_assignment(db, assignment_id)
    try:
        await _apply_k8s_assignment_validation(
            db,
            assignment=assignment,
            cluster=cluster,
            ext_cert=ext_cert,
            actor=_actor(request),
            ip_address=_ip(request),
        )
        await db.commit()
        await db.refresh(assignment)
        return _assignment_read(assignment, cluster, ext_cert)
    except KubernetesApiError as e:
        await db.commit()
        raise HTTPException(status_code=_http_status_from_k8s(e), detail=str(e)) from e
    except Exception as e:
        await db.commit()
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get(
    "/kubernetes/operations",
    response_model=PaginatedResponse[KubernetesSecretOperationRead],
    tags=["control / kubernetes"],
    summary="Kubernetes Secret 操作记录",
)
async def list_kubernetes_secret_operations(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    base = select(KubernetesSecretOperation)
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    result = await db.execute(
        base.order_by(KubernetesSecretOperation.started_at.desc()).offset(skip).limit(limit)
    )
    return PaginatedResponse(items=list(result.scalars().all()), total=total, skip=skip, limit=limit)
