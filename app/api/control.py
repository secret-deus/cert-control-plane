"""Control API – admin-facing endpoints (X-Admin-API-Key auth)."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import write_audit
from app.core.crypto import encrypt_key, decrypt_key
from app.core.security import generate_agent_token, verify_admin_key
from app.database import get_db
from app.models import (
    Agent,
    AgentCertAssignment,
    AgentStatus,
    AuditLog,
    Certificate,
    ExternalCertificate,
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
    AgentCreate,
    AgentRead,
    AuditLogRead,
    CertRead,
    CertSummary,
    ExternalCertCreate,
    ExternalCertRead,
    ExternalCertSummary,
    ExternalCertUploadResponse,
    PaginatedResponse,
    RolloutCreate,
    RolloutDetail,
    RolloutRead,
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
    base = select(Agent)
    if status_filter:
        base = base.where(Agent.status == status_filter)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    result = await db.execute(base.offset(skip).limit(limit).order_by(Agent.created_at.desc()))
    return PaginatedResponse(items=list(result.scalars().all()), total=total, skip=skip, limit=limit)


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

    # Parse certificate
    try:
        cert = x509.load_pem_x509_certificate(body.cert_pem.encode())
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid certificate PEM: {e}")

    # Extract CN
    cn_attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if not cn_attrs:
        raise HTTPException(status_code=400, detail="Certificate missing Common Name")
    subject_cn = cn_attrs[0].value

    # Extract serial
    serial_hex = format(cert.serial_number, 'x').lower()

    # Encrypt private key
    key_encrypted = encrypt_key(body.key_pem.encode(), settings.ca_key_encryption_key)

    # Create external certificate record
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
    await db.flush()

    await write_audit(
        db,
        action="external_cert_uploaded",
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
        message="Certificate uploaded. Use /agents/{id}/assign-cert to assign to agents.",
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
    total_result = await db.execute(select(func.count()).select_from(ExternalCertificate))
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
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    result = await db.execute(base.offset(skip).limit(limit).order_by(Rollout.created_at.desc()))
    return PaginatedResponse(items=list(result.scalars().all()), total=total, skip=skip, limit=limit)


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
        raise HTTPException(status_code=409, detail=str(e))
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
        raise HTTPException(status_code=409, detail=str(e))
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
        raise HTTPException(status_code=409, detail=str(e))
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
`cert_assigned` / `cert_assignment_deleted` /
`external_cert_uploaded` /
`agent_fetch_certs` /
`rollout_created` / `rollout_started` / `rollout_batch_started` /
`rollout_paused` / `rollout_resumed` /
`rollout_completed` / `rollout_failed` / `rollout_rolled_back` / `cert_rolled_back`
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
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    result = await db.execute(base.offset(skip).limit(limit).order_by(AuditLog.created_at.desc()))
    return PaginatedResponse(items=list(result.scalars().all()), total=total, skip=skip, limit=limit)


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
