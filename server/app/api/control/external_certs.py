"""Control API – External certificate upload / query / delete."""

import os
import uuid
from datetime import datetime, timezone

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

from app.core.audit import write_audit
from app.core.crypto import encrypt_key
from app.config import get_settings
from app.database import get_db
from app.models import (
    Agent,
    AgentCertAssignment,
    AgentStatus,
    ExternalCertificate,
)
from app.schemas import (
    ExternalCertCreate,
    ExternalCertRead,
    ExternalCertSummary,
    ExternalCertUploadResponse,
    ExternalCertArchiveUploadResponse,
    FilesDetected,
    PaginatedResponse,
)
from app.services.archive_parser import ArchiveParser

from app.api.control._helpers import _actor, _ip

router = APIRouter()


async def _get_assignments_for_cert(
    db: AsyncSession, cert_id: uuid.UUID
) -> list[AgentCertAssignment]:
    result = await db.execute(
        select(AgentCertAssignment).where(
            AgentCertAssignment.external_cert_id == cert_id
        )
    )
    return list(result.scalars().all())


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
