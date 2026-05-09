"""Control API – admin-facing endpoints (X-Admin-API-Key auth)."""

import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    status,
    UploadFile,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import write_audit
from app.core.crypto import decrypt_key, encrypt_key
from app.core.security import generate_agent_token, verify_admin_key
from app.database import get_db
from app.models import (
    Agent,
    AgentCertAssignment,
    AgentStatus,
    AuditLog,
    Certificate,
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
    Rollout,
    RolloutStatus,
)
from app.orchestrator.rollout import (
    create_rollout,
    pause_rollout,
    resume_rollout,
    rollback_rollout,
)
from app.schemas import (
    AgentCertAssignRequest,
    AgentCertAssignmentRead,
    BatchAssignRequest,
    BatchAssignResult,
    AgentCreate,
    AgentDetailRead,
    AgentRead,
    AuditLogRead,
    CertRead,
    CertSummary,
    ExternalCertCreate,
    ExternalCertRead,
    ExternalCertSummary,
    ExternalCertUploadResponse,
    ExternalCertArchiveUploadResponse,
    FilesDetected,
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
    RolloutCreate,
    RolloutDetail,
    RolloutRead,
)
from app.services.archive_parser import ArchiveParser
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
from app.config import get_settings

router = APIRouter(
    prefix="/api/control",
    dependencies=[Depends(verify_admin_key)],
)


# ===========================================================================
# Agents
# ===========================================================================


@router.post(
    "/agents",
    response_model=AgentRead,
    status_code=status.HTTP_201_CREATED,
    tags=["control / agents"],
    summary="预创建 Agent 条目",
    description="""
在控制平面预创建 Agent 条目（仅保留名称和描述）。

Agent 端启动后会自动调用 `POST /api/agent/register` 发送指纹并等待管理员审批。

**注：** 也可以不预创建，Agent 首次注册时会自动创建条目。
    """,
    responses={
        201: {"description": "Agent 预创建成功"},
        409: {"description": "Agent 名称已存在"},
    },
)
async def create_agent(
    body: AgentCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(Agent).where(Agent.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Agent name already exists")

    agent = Agent(
        name=body.name,
        description=body.description,
        status=AgentStatus.PENDING_APPROVAL,
    )
    db.add(agent)
    await db.flush()

    await write_audit(
        db,
        action="agent_created",
        entity_type="agent",
        entity_id=agent.id,
        actor=_actor(request),
        details={"name": agent.name},
        ip_address=_ip(request),
    )
    await db.commit()
    await db.refresh(agent)
    return agent


@router.get(
    "/agents",
    response_model=PaginatedResponse[AgentRead],
    tags=["control / agents"],
    summary="Agent 列表",
    description="分页查询所有 Agent，可按 `status` 过滤。",
)
async def list_agents(
    status_filter: AgentStatus | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timedelta, timezone

    base = select(Agent)
    if status_filter:
        base = base.where(Agent.status == status_filter)
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    result = await db.execute(
        base.offset(skip).limit(limit).order_by(Agent.created_at.desc())
    )
    agents = list(result.scalars().all())

    # Enhance agents with liveness and cert counts
    now = datetime.now(tz=timezone.utc)
    enhanced_agents = []

    for agent in agents:
        # Calculate liveness
        liveness = "offline"  # Default to offline if never seen
        if agent.last_seen:
            diff = (now - agent.last_seen).total_seconds()
            if diff < 90:  # 1.5x heartbeat interval (30s)
                liveness = "online"
            elif diff < 300:
                liveness = "delayed"
            # else stays "offline"

        # Count certificates
        cert_result = await db.execute(
            select(func.count())
            .select_from(AgentCertAssignment)
            .where(AgentCertAssignment.agent_id == agent.id)
        )
        cert_count = cert_result.scalar_one()

        # Count expiring soon (within 30 days)
        soon = now + timedelta(days=30)
        expiring_result = await db.execute(
            select(func.count())
            .select_from(AgentCertAssignment)
            .join(
                ExternalCertificate,
                AgentCertAssignment.external_cert_id == ExternalCertificate.id,
            )
            .where(
                AgentCertAssignment.agent_id == agent.id,
                ExternalCertificate.not_after <= soon,
            )
        )
        expiring_soon_count = expiring_result.scalar_one()

        # Create enhanced agent dict
        agent_dict = agent.__dict__.copy()
        agent_dict.pop("_sa_instance_state", None)
        agent_dict["liveness"] = liveness
        agent_dict["cert_count"] = cert_count
        agent_dict["expiring_soon_count"] = expiring_soon_count
        enhanced_agents.append(agent_dict)

    return PaginatedResponse(items=enhanced_agents, total=total, skip=skip, limit=limit)


@router.get(
    "/agents/{agent_id}",
    response_model=AgentRead,
    tags=["control / agents"],
    summary="查询单个 Agent",
    responses={404: {"description": "Agent 不存在"}},
)
async def get_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.get(
    "/agents/{agent_id}/detail",
    response_model=AgentDetailRead,
    tags=["control / agents"],
    summary="查询 Agent 详情（含证书列表）",
    description="获取 Agent 详细信息，包括分配的证书列表和到期时间。",
    responses={404: {"description": "Agent 不存在"}},
)
async def get_agent_detail(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timezone

    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Calculate liveness
    now = datetime.now(tz=timezone.utc)
    liveness = None
    if agent.last_seen:
        diff = (now - agent.last_seen).total_seconds()
        if diff < 90:
            liveness = "online"
        elif diff < 300:
            liveness = "delayed"
        else:
            liveness = "offline"

    # Get certificate assignments with external cert details
    cert_result = await db.execute(
        select(AgentCertAssignment, ExternalCertificate)
        .join(
            ExternalCertificate,
            AgentCertAssignment.external_cert_id == ExternalCertificate.id,
        )
        .where(AgentCertAssignment.agent_id == agent_id)
        .order_by(ExternalCertificate.not_after.asc())
    )

    certs = []
    expiring_soon_count = 0

    for assignment, ext_cert in cert_result.all():
        days_remaining = (ext_cert.not_after - now).days

        # Determine urgency
        if days_remaining < 0:
            urgency = "expired"
        elif days_remaining <= 7:
            urgency = "critical"
        elif days_remaining <= 14:
            urgency = "warning"
        else:
            urgency = "normal"

        if days_remaining <= 30:
            expiring_soon_count += 1

        certs.append(
            {
                "local_path": assignment.local_path,
                "cert_name": ext_cert.name,
                "subject_cn": ext_cert.subject_cn,
                "not_after": ext_cert.not_after,
                "days_remaining": days_remaining,
                "urgency": urgency,
            }
        )

    # Build enhanced agent response
    agent_dict = agent.__dict__.copy()
    agent_dict.pop("_sa_instance_state", None)
    agent_dict["liveness"] = liveness
    agent_dict["cert_count"] = len(certs)
    agent_dict["expiring_soon_count"] = expiring_soon_count
    agent_dict["certs"] = certs

    return agent_dict


@router.delete(
    "/agents/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["control / agents"],
    summary="删除 Agent",
)
async def delete_agent(
    agent_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await write_audit(
        db,
        action="agent_deleted",
        entity_type="agent",
        entity_id=agent_id,
        actor=_actor(request),
        ip_address=_ip(request),
    )
    await db.delete(agent)
    await db.commit()


@router.post(
    "/agents/{agent_id}/approve",
    response_model=AgentRead,
    tags=["control / agents"],
    summary="审批通过 Agent 注册",
    description="""
审批通过等待中的 Agent，生成并颁发 `agent_token`。

Agent 凭 `agent_token` 在 `X-Agent-Token` 请求头中认证，拉取证书和发送心跳。
    """,
    responses={
        200: {"description": "审批成功，agent_token 已生成"},
        404: {"description": "Agent 不存在"},
        409: {"description": "Agent 已激活"},
    },
)
async def approve_agent(
    agent_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.status == AgentStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="Agent is already active")
    if not agent.fingerprint:
        raise HTTPException(
            status_code=409,
            detail="Agent has not self-registered yet",
        )

    agent.agent_token = generate_agent_token()
    agent.status = AgentStatus.ACTIVE
    db.add(agent)

    await write_audit(
        db,
        action="agent_approved",
        entity_type="agent",
        entity_id=agent_id,
        actor=_actor(request),
        details={"name": agent.name},
        ip_address=_ip(request),
    )
    await db.commit()
    await db.refresh(agent)
    return agent


@router.post(
    "/agents/{agent_id}/reject",
    response_model=AgentRead,
    tags=["control / agents"],
    summary="拒绝 Agent 注册",
    description="将 pending_approval 状态的 Agent 标记为 revoked（拒绝注册）。",
    responses={
        200: {"description": "拒绝成功"},
        404: {"description": "Agent 不存在"},
    },
)
async def reject_agent(
    agent_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent.status = AgentStatus.REVOKED
    agent.agent_token = None
    db.add(agent)

    await write_audit(
        db,
        action="agent_rejected",
        entity_type="agent",
        entity_id=agent_id,
        actor=_actor(request),
        details={"name": agent.name},
        ip_address=_ip(request),
    )
    await db.commit()
    await db.refresh(agent)
    return agent


# ===========================================================================
# External Certificates
# ===========================================================================


@router.post(
    "/external-certs",
    response_model=ExternalCertUploadResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["control / external-certs"],
    summary="上传外部证书",
    description="""
上传从第三方证书提供商（如阿里云、Let's Encrypt）购买的证书。

- 私钥会被 Fernet 加密后存储
- 证书会被解析提取 CN、序列号、有效期等信息
- 上传后需要通过 `/agents/{id}/assign-cert` 分配给 Agent
    """,
)
async def upload_external_cert(
    body: ExternalCertCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    from cryptography import x509
    from cryptography.x509.oid import NameOID

    settings = get_settings()

    try:
        cert = x509.load_pem_x509_certificate(body.cert_pem.encode())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid certificate PEM: {e}") from e

    cn_attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if not cn_attrs:
        raise HTTPException(status_code=400, detail="Certificate missing Common Name")
    subject_cn = cn_attrs[0].value

    serial_hex = format(cert.serial_number, "x").lower()

    existing_by_serial = await db.execute(
        select(ExternalCertificate).where(ExternalCertificate.serial_hex == serial_hex)
    )
    if existing_by_serial.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Certificate with serial {serial_hex} already exists. "
            f"Subject CN: {subject_cn}",
        )

    existing_by_cn = await db.execute(
        select(ExternalCertificate)
        .where(ExternalCertificate.subject_cn == subject_cn, ExternalCertificate.is_active.is_(True))
        .order_by(ExternalCertificate.not_after.desc())
        .limit(1)
    )
    old_cert = existing_by_cn.scalar_one_or_none()

    key_encrypted = encrypt_key(body.key_pem.encode(), settings.ca_key_encryption_key)

    if old_cert:
        # Migrate all assignments from other same-CN certs to the renewed cert
        other_same_cn = await db.execute(
            select(ExternalCertificate).where(
                ExternalCertificate.subject_cn == subject_cn,
                ExternalCertificate.is_active.is_(True),
                ExternalCertificate.id != old_cert.id,
            )
        )
        for stale_cert in other_same_cn.scalars().all():
            stale_assignments = await db.execute(
                select(AgentCertAssignment).where(
                    AgentCertAssignment.external_cert_id == stale_cert.id
                )
            )
            for assignment in stale_assignments.scalars().all():
                assignment.external_cert_id = old_cert.id
                db.add(assignment)
            stale_cert.is_active = False
            db.add(stale_cert)

        old_cert.name = body.name
        old_cert.description = body.description
        old_cert.cert_pem = body.cert_pem
        old_cert.key_pem_encrypted = key_encrypted
        old_cert.chain_pem = body.chain_pem
        old_cert.serial_hex = serial_hex
        old_cert.not_before = cert.not_valid_before_utc
        old_cert.not_after = cert.not_valid_after_utc
        old_cert.provider = body.provider
        old_cert.external_id = body.external_id
        old_cert.updated_at = datetime.now(timezone.utc)
        db.add(old_cert)
        external_cert = old_cert
        action = "external_cert_renewed"
        message = f"Certificate renewed. {len(await _get_assignments_for_cert(db, old_cert.id))} agents will receive update."
    else:
        external_cert = ExternalCertificate(
            name=body.name,
            description=body.description,
            cert_pem=body.cert_pem,
            key_pem_encrypted=key_encrypted,
            chain_pem=body.chain_pem,
            subject_cn=subject_cn,
            serial_hex=serial_hex,
            not_before=cert.not_valid_before_utc,
            not_after=cert.not_valid_after_utc,
            provider=body.provider,
            external_id=body.external_id,
        )
        db.add(external_cert)
        action = "external_cert_uploaded"
        message = (
            "Certificate uploaded. Use /agents/{id}/assign-cert to assign to agents."
        )

    await db.flush()

    # Auto-assign: find agents with cert_paths containing this domain
    auto_assigned = 0
    agents_result = await db.execute(
        select(Agent).where(Agent.status == AgentStatus.ACTIVE, Agent.cert_paths.isnot(None))
    )
    active_agents = agents_result.scalars().all()

    for agent in active_agents:
        if not agent.cert_paths:
            continue
        for path in agent.cert_paths:
            filename = os.path.basename(path)
            domain_from_path = filename.rsplit(".", 1)[0] if "." in filename else filename
            if domain_from_path == subject_cn:
                existing = await db.execute(
                    select(AgentCertAssignment).where(
                        AgentCertAssignment.agent_id == agent.id,
                        AgentCertAssignment.local_path == path,
                    )
                )
                if not existing.scalar_one_or_none():
                    assignment = AgentCertAssignment(
                        agent_id=agent.id,
                        external_cert_id=external_cert.id,
                        local_path=path,
                    )
                    db.add(assignment)
                    auto_assigned += 1

    if auto_assigned > 0:
        message = f"Certificate uploaded and auto-assigned to {auto_assigned} agent(s)."
        action = "external_cert_uploaded_auto_assigned"

    await db.flush()

    await write_audit(
        db,
        action=action,
        entity_type="external_certificate",
        entity_id=external_cert.id,
        actor=_actor(request),
        details={
            "name": body.name,
            "provider": body.provider,
            "subject_cn": subject_cn,
            "serial_hex": serial_hex,
        },
        ip_address=_ip(request),
    )
    await db.commit()
    await db.refresh(external_cert)

    return ExternalCertUploadResponse(
        id=external_cert.id,
        name=external_cert.name,
        subject_cn=external_cert.subject_cn,
        serial_hex=external_cert.serial_hex,
        not_after=external_cert.not_after,
        message=message,
    )


@router.post(
    "/external-certs/upload-archive",
    response_model=ExternalCertArchiveUploadResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["control / external-certs"],
    summary="上传证书压缩包",
    description="""
上传证书压缩包（.zip / .tar.gz / .tgz），自动解析并创建证书记录。

- 支持证书文件后缀 `.pem` / `.crt` / `.cer`
- 支持私钥文件后缀 `.key` / `.pem`
- 自动按 PEM 内容识别证书、私钥和证书链，不强依赖文件名
- 私钥会被 Fernet 加密后存储
- 支持 `fullchain.pem` / `chain.pem` / `bundle.crt` 等链文件
    """,
)
async def upload_cert_archive(
    archive: UploadFile = File(...),
    name: str | None = Form(None),
    provider: str | None = Form(None),
    description: str | None = Form(None),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()

    archive_bytes = await archive.read()

    parsed = ArchiveParser.parse(archive_bytes, archive.filename or "archive.zip")

    key_encrypted = encrypt_key(parsed.key_pem.encode(), settings.ca_key_encryption_key)

    cert_name = name or parsed.metadata.subject_cn

    existing_by_serial = await db.execute(
        select(ExternalCertificate).where(
            ExternalCertificate.serial_hex == parsed.metadata.serial_hex
        )
    )
    if existing_by_serial.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Certificate with serial {parsed.metadata.serial_hex} already exists. "
            f"Subject CN: {parsed.metadata.subject_cn}",
        )

    existing_by_cn = await db.execute(
        select(ExternalCertificate).where(
            ExternalCertificate.subject_cn == parsed.metadata.subject_cn
        )
    )
    old_cert = existing_by_cn.scalar_one_or_none()

    if old_cert:
        old_cert.name = cert_name
        old_cert.description = description
        old_cert.cert_pem = parsed.cert_pem
        old_cert.key_pem_encrypted = key_encrypted
        old_cert.chain_pem = parsed.chain_pem
        old_cert.serial_hex = parsed.metadata.serial_hex
        old_cert.not_before = parsed.metadata.not_before
        old_cert.not_after = parsed.metadata.not_after
        old_cert.provider = provider or "manual"
        old_cert.updated_at = datetime.now(timezone.utc)
        db.add(old_cert)
        external_cert = old_cert
        action = "external_cert_renewed_from_archive"
        assignment_count = len(await _get_assignments_for_cert(db, old_cert.id))
        message = f"Certificate renewed from archive. {assignment_count} agents will receive update."
    else:
        external_cert = ExternalCertificate(
            name=cert_name,
            description=description,
            cert_pem=parsed.cert_pem,
            key_pem_encrypted=key_encrypted,
            chain_pem=parsed.chain_pem,
            subject_cn=parsed.metadata.subject_cn,
            serial_hex=parsed.metadata.serial_hex,
            not_before=parsed.metadata.not_before,
            not_after=parsed.metadata.not_after,
            provider=provider or "manual",
            external_id=None,
        )
        db.add(external_cert)
        action = "external_cert_uploaded_from_archive"
        message = "Certificate uploaded from archive."

    await db.flush()

    await write_audit(
        db,
        action=action,
        entity_type="external_certificate",
        entity_id=external_cert.id,
        actor=_actor(request),
        details={
            "name": cert_name,
            "provider": provider or "manual",
            "subject_cn": parsed.metadata.subject_cn,
            "serial_hex": parsed.metadata.serial_hex,
            "files": {
                "cert": parsed.cert_filename,
                "key": parsed.key_filename,
                "chain": parsed.chain_filename,
            },
        },
        ip_address=_ip(request),
    )
    await db.commit()
    await db.refresh(external_cert)

    return ExternalCertArchiveUploadResponse(
        id=external_cert.id,
        name=external_cert.name,
        subject_cn=external_cert.subject_cn,
        serial_hex=external_cert.serial_hex,
        not_after=external_cert.not_after,
        files_detected=FilesDetected(
            cert=parsed.cert_filename,
            key=parsed.key_filename,
            chain=parsed.chain_filename,
        ),
        san_domains=parsed.metadata.san_domains,
        message=message,
    )


@router.get(
    "/external-certs",
    response_model=PaginatedResponse[ExternalCertSummary],
    tags=["control / external-certs"],
    summary="列出外部证书",
)
async def list_external_certs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    total_result = await db.execute(
        select(func.count()).select_from(ExternalCertificate)
    )
    total = total_result.scalar()

    result = await db.execute(
        select(ExternalCertificate)
        .order_by(ExternalCertificate.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    items = list(result.scalars().all())

    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@router.get(
    "/external-certs/{cert_id}",
    response_model=ExternalCertRead,
    tags=["control / external-certs"],
    summary="获取外部证书详情",
)
async def get_external_cert(cert_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    cert = await db.get(ExternalCertificate, cert_id)
    if not cert:
        raise HTTPException(status_code=404, detail="External certificate not found")
    return cert


@router.delete(
    "/external-certs/{cert_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["control / external-certs"],
    summary="删除外部证书",
    description="""
删除指定的外部证书记录。

**注意**：
- 如果证书已分配给 Agent，会同时删除关联记录
- 此操作不可逆，请谨慎操作
    """,
)
async def delete_external_cert(
    cert_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    cert = await db.get(ExternalCertificate, cert_id)
    if not cert:
        raise HTTPException(status_code=404, detail="External certificate not found")

    cert_name = cert.name
    cert_cn = cert.subject_cn

    assignments_result = await db.execute(
        select(AgentCertAssignment).where(
            AgentCertAssignment.external_cert_id == cert_id
        )
    )
    assignments = assignments_result.scalars().all()
    for assignment in assignments:
        await db.delete(assignment)

    await db.delete(cert)

    await write_audit(
        db,
        action="external_cert_deleted",
        entity_type="external_certificate",
        entity_id=cert_id,
        actor=_actor(request),
        details={
            "name": cert_name,
            "subject_cn": cert_cn,
            "assignments_deleted": len(assignments),
        },
        ip_address=_ip(request),
    )
    await db.commit()


# ===========================================================================
# Kubernetes Secrets
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


# ===========================================================================
# Agent Cert Assignments
# ===========================================================================


@router.post(
    "/agents/{agent_id}/assign-cert",
    response_model=AgentCertAssignmentRead,
    status_code=status.HTTP_201_CREATED,
    tags=["control / external-certs"],
    summary="为 Agent 分配证书",
    description="""
将外部证书分配给指定 Agent 的某个本地路径。

Agent 下次调用 `/fetch-certs` 时，会对比该路径的证书有效期并拉取更新。

**示例：**
```json
{
  "external_cert_id": "uuid-of-cert",
  "local_path": "/etc/nginx/ssl/api.example.com.crt"
}
```
    """,
)
async def assign_cert_to_agent(
    agent_id: uuid.UUID,
    body: AgentCertAssignRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    ext_cert = await db.get(ExternalCertificate, body.external_cert_id)
    if not ext_cert:
        raise HTTPException(status_code=404, detail="External certificate not found")

    # Upsert: if assignment for this agent+path already exists, update the cert
    existing_result = await db.execute(
        select(AgentCertAssignment).where(
            AgentCertAssignment.agent_id == agent_id,
            AgentCertAssignment.local_path == body.local_path,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        existing.external_cert_id = body.external_cert_id
        db.add(existing)
        assignment = existing
    else:
        assignment = AgentCertAssignment(
            agent_id=agent_id,
            external_cert_id=body.external_cert_id,
            local_path=body.local_path,
        )
        db.add(assignment)

    await db.flush()

    await write_audit(
        db,
        action="cert_assigned",
        entity_type="agent_cert_assignment",
        entity_id=assignment.id,
        actor=_actor(request),
        details={
            "agent_name": agent.name,
            "local_path": body.local_path,
            "external_cert_name": ext_cert.name,
        },
        ip_address=_ip(request),
    )
    await db.commit()
    await db.refresh(assignment)
    return assignment


@router.post(
    "/certs/deploy",
    response_model=BatchAssignResult,
    status_code=status.HTTP_201_CREATED,
    tags=["control / external-certs"],
    summary="批量部署证书到多个 Agent",
    description="""
将外部证书批量部署到多个 Agent。

指定证书 ID、目标 Agent 列表和本地路径，系统会为每个 Agent 创建分配。
Agent 下次心跳时会自动拉取最新证书并部署。
    """,
)
async def batch_deploy_cert(
    body: BatchAssignRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ext_cert = await db.get(ExternalCertificate, body.external_cert_id)
    if not ext_cert:
        raise HTTPException(status_code=404, detail="External certificate not found")

    assignments = []
    success = 0
    failed = 0

    for agent_id in body.agent_ids:
        agent = await db.get(Agent, agent_id)
        if not agent or agent.status != AgentStatus.ACTIVE:
            failed += 1
            continue

        existing_result = await db.execute(
            select(AgentCertAssignment).where(
                AgentCertAssignment.agent_id == agent_id,
                AgentCertAssignment.local_path == body.local_path,
            )
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            existing.external_cert_id = body.external_cert_id
            db.add(existing)
            assignments.append(existing)
        else:
            assignment = AgentCertAssignment(
                agent_id=agent_id,
                external_cert_id=body.external_cert_id,
                local_path=body.local_path,
            )
            db.add(assignment)
            assignments.append(assignment)
        success += 1

    if assignments:
        await db.flush()

        await write_audit(
            db,
            action="cert_batch_deployed",
            entity_type="external_certificate",
            entity_id=body.external_cert_id,
            actor=_actor(request),
            details={
                "cert_name": ext_cert.name,
                "target_agents": success,
                "local_path": body.local_path,
            },
            ip_address=_ip(request),
        )

    await db.commit()
    for a in assignments:
        await db.refresh(a)

    return BatchAssignResult(
        success=success,
        failed=failed,
        assignments=assignments,
    )


@router.get(
    "/agents/{agent_id}/assignments",
    response_model=list[AgentCertAssignmentRead],
    tags=["control / external-certs"],
    summary="查看 Agent 的证书分配",
)
async def list_agent_assignments(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    result = await db.execute(
        select(AgentCertAssignment)
        .where(AgentCertAssignment.agent_id == agent_id)
        .order_by(AgentCertAssignment.created_at.desc())
    )
    return list(result.scalars().all())


@router.delete(
    "/agents/{agent_id}/assignments/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["control / external-certs"],
    summary="删除证书分配",
)
async def delete_assignment(
    agent_id: uuid.UUID,
    assignment_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    assignment = await db.get(AgentCertAssignment, assignment_id)
    if not assignment or assignment.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Assignment not found")

    await write_audit(
        db,
        action="cert_assignment_deleted",
        entity_type="agent_cert_assignment",
        entity_id=assignment_id,
        actor=_actor(request),
        ip_address=_ip(request),
    )
    await db.delete(assignment)
    await db.commit()


# ===========================================================================
# Certificates (audit records)
# ===========================================================================


@router.get(
    "/agents/{agent_id}/certs",
    response_model=list[CertSummary],
    tags=["control / certificates"],
    summary="Agent 证书历史",
    responses={404: {"description": "Agent 不存在"}},
)
async def list_agent_certs(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Certificate)
        .where(Certificate.agent_id == agent_id)
        .order_by(Certificate.created_at.desc())
    )
    return list(result.scalars().all())


@router.get(
    "/certs/{cert_id}",
    response_model=CertRead,
    tags=["control / certificates"],
    summary="查询单张证书",
    responses={404: {"description": "证书不存在"}},
)
async def get_cert(cert_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    cert = await db.get(Certificate, cert_id)
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    return cert


# ===========================================================================
# Rollouts
# ===========================================================================


@router.post(
    "/rollouts",
    response_model=RolloutRead,
    status_code=status.HTTP_201_CREATED,
    tags=["control / rollouts"],
    summary="创建 Rollout",
)
async def create_rollout_endpoint(
    body: RolloutCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    rollout = await create_rollout(
        db,
        name=body.name,
        description=body.description,
        batch_size=body.batch_size,
        target_filter=body.target_filter,
        created_by=_actor(request),
    )
    await write_audit(
        db,
        action="rollout_created",
        entity_type="rollout",
        entity_id=rollout.id,
        actor=_actor(request),
        details={"name": rollout.name, "total_batches": rollout.total_batches},
        ip_address=_ip(request),
    )
    await db.commit()
    await db.refresh(rollout)
    return rollout


@router.get(
    "/rollouts",
    response_model=PaginatedResponse[RolloutRead],
    tags=["control / rollouts"],
    summary="Rollout 列表",
)
async def list_rollouts(
    status_filter: RolloutStatus | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    base = select(Rollout)
    if status_filter:
        base = base.where(Rollout.status == status_filter)
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    result = await db.execute(
        base.offset(skip).limit(limit).order_by(Rollout.created_at.desc())
    )
    return PaginatedResponse(
        items=list(result.scalars().all()), total=total, skip=skip, limit=limit
    )


@router.get(
    "/rollouts/{rollout_id}",
    response_model=RolloutDetail,
    tags=["control / rollouts"],
    summary="Rollout 详情",
    responses={404: {"description": "Rollout 不存在"}},
)
async def get_rollout(rollout_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Rollout)
        .where(Rollout.id == rollout_id)
        .options(selectinload(Rollout.items))
    )
    rollout = result.scalar_one_or_none()
    if not rollout:
        raise HTTPException(status_code=404, detail="Rollout not found")
    return rollout


@router.post(
    "/rollouts/{rollout_id}/start",
    response_model=RolloutRead,
    tags=["control / rollouts"],
    summary="启动 Rollout",
)
async def start_rollout(
    rollout_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    rollout = await db.get(Rollout, rollout_id)
    if not rollout:
        raise HTTPException(status_code=404, detail="Rollout not found")
    if rollout.status != RolloutStatus.PENDING:
        raise HTTPException(
            status_code=409, detail=f"Cannot start rollout in status '{rollout.status}'"
        )
    rollout.status = RolloutStatus.RUNNING
    db.add(rollout)
    await write_audit(
        db,
        action="rollout_started",
        entity_type="rollout",
        entity_id=rollout_id,
        actor=_actor(request),
        ip_address=_ip(request),
    )
    await db.commit()
    await db.refresh(rollout)
    return rollout


@router.post(
    "/rollouts/{rollout_id}/pause",
    response_model=RolloutRead,
    tags=["control / rollouts"],
    summary="暂停 Rollout",
)
async def pause_rollout_endpoint(
    rollout_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    rollout = await db.get(Rollout, rollout_id)
    if not rollout:
        raise HTTPException(status_code=404, detail="Rollout not found")
    try:
        rollout = await pause_rollout(db, rollout, actor=_actor(request))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    await db.commit()
    await db.refresh(rollout)
    return rollout


@router.post(
    "/rollouts/{rollout_id}/resume",
    response_model=RolloutRead,
    tags=["control / rollouts"],
    summary="恢复 Rollout",
)
async def resume_rollout_endpoint(
    rollout_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    rollout = await db.get(Rollout, rollout_id)
    if not rollout:
        raise HTTPException(status_code=404, detail="Rollout not found")
    try:
        rollout = await resume_rollout(db, rollout, actor=_actor(request))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    await db.commit()
    await db.refresh(rollout)
    return rollout


@router.post(
    "/rollouts/{rollout_id}/rollback",
    response_model=RolloutRead,
    tags=["control / rollouts"],
    summary="回滚 Rollout",
)
async def rollback_rollout_endpoint(
    rollout_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    rollout = await db.get(Rollout, rollout_id)
    if not rollout:
        raise HTTPException(status_code=404, detail="Rollout not found")
    try:
        rollout = await rollback_rollout(db, rollout, actor=_actor(request))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    await db.commit()
    await db.refresh(rollout)
    return rollout


# ===========================================================================
# Audit
# ===========================================================================


@router.get(
    "/audit",
    response_model=PaginatedResponse[AuditLogRead],
    tags=["control / audit"],
    summary="审计日志",
    description="""
查询所有写操作的不可变审计记录（按时间倒序）。

**覆盖的操作：**
`agent_created` / `agent_registered` / `agent_approved` / `agent_rejected` / `agent_deleted` /
`cert_assigned` / `cert_batch_deployed` / `cert_assignment_deleted` /
`external_cert_uploaded` / `external_cert_uploaded_auto_assigned` /
`external_cert_renewed` / `external_cert_uploaded_from_archive` /
`external_cert_renewed_from_archive` / `external_cert_deleted` /
`agent_fetch_certs` / `agent_report_certs` /
`rollout_created` / `rollout_started` / `rollout_batch_started` /
`rollout_paused` / `rollout_resumed` /
`rollout_completed` / `rollout_failed` / `rollout_rolled_back` / `cert_rolled_back` /
`kubernetes_cluster_created` / `kubernetes_cluster_connection_tested` /
`kubernetes_cluster_credentials_updated` /
`kubernetes_secret_assignment_created` / `kubernetes_secret_assignment_deleted` /
`kubernetes_secret_dry_run_created` / `kubernetes_secret_deployed` /
`kubernetes_secret_adopted` / `kubernetes_secret_rolled_back` /
`kubernetes_secret_validated`
    """,
)
async def list_audit_logs(
    entity_type: str | None = Query(None),
    entity_id: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    base = select(AuditLog)
    if entity_type:
        base = base.where(AuditLog.entity_type == entity_type)
    if entity_id:
        base = base.where(AuditLog.entity_id == entity_id)
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    result = await db.execute(
        base.offset(skip).limit(limit).order_by(AuditLog.created_at.desc())
    )
    return PaginatedResponse(
        items=list(result.scalars().all()), total=total, skip=skip, limit=limit
    )


# ===========================================================================
# Helpers
# ===========================================================================


def _actor(request: Request) -> str:
    api_key = request.headers.get("X-Admin-API-Key", "")
    if api_key and len(api_key) >= 8:
        return f"admin:{api_key[:8]}"
    return "admin"


def _ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


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


async def _get_assignments_for_cert(
    db: AsyncSession, cert_id: uuid.UUID
) -> list[AgentCertAssignment]:
    result = await db.execute(
        select(AgentCertAssignment).where(
            AgentCertAssignment.external_cert_id == cert_id
        )
    )
    return list(result.scalars().all())
