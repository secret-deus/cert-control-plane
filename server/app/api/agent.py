"""Agent API – endpoints called by agents.

Authentication:
  - /register      : no auth (TOFU first contact)
  - /register/status: no auth (poll by agent_id + fingerprint)
  - /heartbeat     : X-Agent-Token header
  - /fetch-certs   : X-Agent-Token header
  - /report-certs  : X-Agent-Token header
"""

import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.audit import write_audit
from app.core.crypto import decrypt_key
from app.database import get_db
from app.models import (
    Agent,
    AgentCertAssignment,
    AgentStatus,
    ExternalCertificate,
    Rollout,
    RolloutItem,
    RolloutItemStatus,
    RolloutStatus,
)
from app.registry.store import get_current_cert, record_deployed_cert
from app.schemas import (
    AgentFetchCertsRequest,
    AgentFetchCertsResponse,
    AgentRegisterRequest,
    AgentRegisterResponse,
    AgentRegisterStatusResponse,
    AgentReportCertsRequest,
    AgentReportCertsResponse,
    CertUpdateItem,
    HeartbeatRequest,
    HeartbeatResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])


# ---------------------------------------------------------------------------
# Auth helper: resolve agent by X-Agent-Token
# ---------------------------------------------------------------------------


async def _resolve_agent_by_token(
    x_agent_token: str | None,
    db: AsyncSession,
) -> Agent:
    """Resolve X-Agent-Token header to an active Agent."""
    if not x_agent_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Agent-Token header is required",
        )
    result = await db.execute(
        select(Agent).where(
            Agent.agent_token == x_agent_token,
            Agent.status == AgentStatus.ACTIVE,
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or inactive agent token",
        )
    return agent


async def _get_active_rollout_item(
    db: AsyncSession,
    *,
    agent_id,
) -> RolloutItem | None:
    """Return the rollout item gating this agent in a RUNNING rollout.

    Returns the IN_PROGRESS item if one exists, otherwise a PENDING item.
    Used to gate fetch-certs: agents with IN_PROGRESS items may pull updates;
    agents with only PENDING items must wait for their batch.
    """
    result = await db.execute(
        select(RolloutItem)
        .join(Rollout, Rollout.id == RolloutItem.rollout_id)
        .where(
            RolloutItem.agent_id == agent_id,
            Rollout.status == RolloutStatus.RUNNING,
            RolloutItem.status.in_(
                (RolloutItemStatus.PENDING, RolloutItemStatus.IN_PROGRESS)
            ),
        )
        .order_by(Rollout.created_at.asc(), RolloutItem.batch_number.asc())
    )
    items = list(result.scalars().all())
    for item in items:
        if item.status == RolloutItemStatus.IN_PROGRESS:
            return item
    return items[0] if items else None


async def _complete_rollout_item_if_ready(
    db: AsyncSession,
    *,
    agent: Agent,
    rollout_item: RolloutItem | None,
) -> None:
    """Mark an in-progress rollout item completed once all assignments are current."""
    if rollout_item is None or rollout_item.status != RolloutItemStatus.IN_PROGRESS:
        return

    now = datetime.now(tz=timezone.utc)
    result = await db.execute(
        select(AgentCertAssignment, ExternalCertificate)
        .join(
            ExternalCertificate,
            ExternalCertificate.id == AgentCertAssignment.external_cert_id,
        )
        .where(
            AgentCertAssignment.agent_id == agent.id,
            ExternalCertificate.is_active.is_(True),
        )
    )
    assignments = list(result.all())

    latest_current = None
    if not assignments:
        rollout_item.status = RolloutItemStatus.COMPLETED
        rollout_item.completed_at = now
        db.add(rollout_item)
        return

    for assignment, ext_cert in assignments:
        current = await get_current_cert(
            db,
            agent.id,
            local_path=assignment.local_path,
        )
        if (
            current is None
            or current.external_cert_id != ext_cert.id
            or current.serial_hex != ext_cert.serial_hex
            or current.not_after != ext_cert.not_after
        ):
            return
        latest_current = current

    rollout_item.status = RolloutItemStatus.COMPLETED
    rollout_item.completed_at = now
    rollout_item.new_cert_id = latest_current.id if latest_current else None
    db.add(rollout_item)


# ---------------------------------------------------------------------------
# POST /api/agent/register  (TOFU)
# ---------------------------------------------------------------------------


@router.post(
    "/register",
    response_model=AgentRegisterResponse,
    status_code=status.HTTP_200_OK,
    summary="Agent TOFU 注册",
    description="""
Agent 首次注册（TOFU：信任首次使用）。

**流程：**
1. Agent 生成 RSA 公私钥，计算 `SHA256(DER public key)` 作为指纹
2. Agent 提交 `{name, fingerprint}`
3. 若该名称不存在 → 创建 Agent，`status=pending_approval`，返回 `{status: "pending", agent_id}`
4. 若该名称已存在且指纹匹配且已激活 → 返回 `{status: "approved", agent_token}`
5. 若指纹不匹配 → 403

**管理员审批后：** Agent 轮询 `GET /api/agent/register/status` 拿到 `agent_token`
    """,
)
async def register_agent(
    body: AgentRegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # Check if agent name already exists
    result = await db.execute(select(Agent).where(Agent.name == body.name))
    existing = result.scalar_one_or_none()

    if existing is None:
        # New agent – create with pending_approval
        agent = Agent(
            name=body.name,
            fingerprint=body.fingerprint,
            status=AgentStatus.PENDING_APPROVAL,
        )
        db.add(agent)
        await db.flush()

        await write_audit(
            db,
            action="agent_registered",
            entity_type="agent",
            entity_id=agent.id,
            actor=agent.name,
            details={"fingerprint": body.fingerprint},
            ip_address=request.client.host if request.client else None,
        )
        await db.commit()
        await db.refresh(agent)

        return AgentRegisterResponse(
            status="pending",
            agent_id=agent.id,
            agent_token=None,
            message="Registration submitted. Waiting for admin approval.",
        )

    # Pre-created agent slot: bind the first observed fingerprint.
    if existing.fingerprint is None:
        if existing.status == AgentStatus.REVOKED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Agent registration has been rejected",
            )

        existing.fingerprint = body.fingerprint
        db.add(existing)
        await write_audit(
            db,
            action="agent_registered",
            entity_type="agent",
            entity_id=existing.id,
            actor=existing.name,
            details={"fingerprint": body.fingerprint, "pre_created": True},
            ip_address=request.client.host if request.client else None,
        )
        await db.commit()
        await db.refresh(existing)

        return AgentRegisterResponse(
            status="pending",
            agent_id=existing.id,
            agent_token=None,
            message="Registration submitted. Waiting for admin approval.",
        )

    # Existing agent
    if existing.fingerprint != body.fingerprint:
        logger.warning(
            "Fingerprint mismatch for agent '%s': presented=%s, stored=%s",
            body.name,
            body.fingerprint,
            existing.fingerprint,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Fingerprint mismatch – potential impersonation attempt",
        )

    if existing.status == AgentStatus.ACTIVE and existing.agent_token:
        # Already approved – return token directly
        return AgentRegisterResponse(
            status="approved",
            agent_id=existing.id,
            agent_token=existing.agent_token,
            message="Agent is approved and active.",
        )

    if existing.status == AgentStatus.REVOKED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent registration has been rejected",
        )

    # Still pending
    return AgentRegisterResponse(
        status="pending",
        agent_id=existing.id,
        agent_token=None,
        message="Awaiting admin approval.",
    )


# ---------------------------------------------------------------------------
# GET /api/agent/register/status  (polling)
# ---------------------------------------------------------------------------


@router.get(
    "/register/status",
    response_model=AgentRegisterStatusResponse,
    summary="查询注册审批状态",
    description="Agent 轮询此端点等待管理员审批，审批通过后返回 `agent_token`。",
)
async def register_status(
    agent_id: str,
    fingerprint: str,
    db: AsyncSession = Depends(get_db),
):
    import uuid as _uuid
    try:
        agent_uuid = _uuid.UUID(agent_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid agent_id format")

    agent = await db.get(Agent, agent_uuid)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.fingerprint != fingerprint:
        raise HTTPException(status_code=403, detail="Fingerprint mismatch")

    if agent.status == AgentStatus.ACTIVE and agent.agent_token:
        return AgentRegisterStatusResponse(
            status="approved",
            agent_token=agent.agent_token,
        )
    elif agent.status == AgentStatus.REVOKED:
        return AgentRegisterStatusResponse(status="rejected")
    else:
        return AgentRegisterStatusResponse(status="pending_approval")


# ---------------------------------------------------------------------------
# POST /api/agent/heartbeat
# ---------------------------------------------------------------------------


@router.post(
    "/heartbeat",
    response_model=HeartbeatResponse,
    summary="心跳上报",
    description="Agent 定期调用，更新 `last_seen` 时间戳。需要 `X-Agent-Token` 认证。",
)
async def heartbeat(
    body: HeartbeatRequest,
    x_agent_token: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    # Dev mode: allow bypass by agent_name in query param (dev only)
    if settings.dev_mode and not x_agent_token:
        # Try to find any active agent for dev convenience
        result = await db.execute(
            select(Agent).where(Agent.status == AgentStatus.ACTIVE).limit(1)
        )
        agent = result.scalar_one_or_none()
        if not agent:
            raise HTTPException(status_code=404, detail="No active agent found")
    else:
        agent = await _resolve_agent_by_token(x_agent_token, db)

    agent.last_seen = datetime.now(tz=timezone.utc)
    db.add(agent)
    await db.commit()
    return HeartbeatResponse(acknowledged=True)


# ---------------------------------------------------------------------------
# POST /api/agent/fetch-certs  (batch)
# ---------------------------------------------------------------------------


@router.post(
    "/fetch-certs",
    response_model=AgentFetchCertsResponse,
    summary="批量拉取证书",
    description="""
Agent 遍历本地证书表，发送 `[{local_path, current_not_after}]`，
平台对比每条路径对应的外部证书有效期，有更新则返回 cert+key+chain。

需要 `X-Agent-Token` 认证。
    """,
)
async def fetch_certs(
    body: AgentFetchCertsRequest,
    request: Request,
    x_agent_token: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()

    # Resolve agent
    if settings.dev_mode and not x_agent_token:
        result = await db.execute(
            select(Agent).where(Agent.status == AgentStatus.ACTIVE).limit(1)
        )
        agent = result.scalar_one_or_none()
        if not agent:
            raise HTTPException(status_code=404, detail="No active agent found (dev mode)")
    else:
        agent = await _resolve_agent_by_token(x_agent_token, db)

    rollout_item = await _get_active_rollout_item(db, agent_id=agent.id)
    updates_allowed = (
        rollout_item is None or rollout_item.status == RolloutItemStatus.IN_PROGRESS
    )

    updates: list[CertUpdateItem] = []

    assignment_result = await db.execute(
        select(AgentCertAssignment).where(AgentCertAssignment.agent_id == agent.id)
    )
    assignments = list(assignment_result.scalars().all())
    assignments_by_path = {assignment.local_path: assignment for assignment in assignments}

    checks_by_path = {check.local_path: check for check in body.certs}
    all_paths = list(checks_by_path.keys())
    reported_paths = list(checks_by_path.keys()) or list(agent.cert_paths or [])
    reported_dirs = {os.path.dirname(path) for path in reported_paths}
    for assignment in assignments:
        assignment_dir = os.path.dirname(assignment.local_path)
        if (
            assignment.local_path not in checks_by_path
            and assignment_dir in reported_dirs
        ):
            all_paths.append(assignment.local_path)

    for local_path in all_paths:
        check = checks_by_path.get(local_path)
        assignment = assignments_by_path.get(local_path)
        current_not_after = check.current_not_after if check else None
        if current_not_after is None and check is None:
            current_snapshot = await get_current_cert(db, agent.id, local_path=local_path)
            if current_snapshot is not None:
                current_not_after = current_snapshot.not_after

        if assignment is None:
            # No assignment for this path
            updates.append(CertUpdateItem(
                local_path=local_path,
                has_update=False,
            ))
            continue

        # Load external cert
        ext_cert: ExternalCertificate | None = await db.get(
            ExternalCertificate, assignment.external_cert_id
        )
        if ext_cert is None or not ext_cert.is_active:
            updates.append(CertUpdateItem(
                local_path=local_path,
                has_update=False,
            ))
            continue

        if (
            current_not_after is not None
            and current_not_after >= ext_cert.not_after
        ):
            await record_deployed_cert(
                db,
                agent_id=agent.id,
                local_path=local_path,
                external_cert=ext_cert,
            )

        # Compare not_after: update if server cert is newer
        has_update = (
            current_not_after is None
            or ext_cert.not_after > current_not_after
        )

        if has_update and not updates_allowed:
            updates.append(CertUpdateItem(
                local_path=local_path,
                has_update=False,
                not_after=ext_cert.not_after,
            ))
            continue

        if not has_update:
            updates.append(CertUpdateItem(
                local_path=local_path,
                has_update=False,
                not_after=ext_cert.not_after,
            ))
            continue

        # Decrypt private key
        try:
            key_pem = decrypt_key(
                ext_cert.key_pem_encrypted, settings.ca_key_encryption_key
            ).decode()
        except Exception:
            logger.exception(
                "Failed to decrypt key for cert %s (assignment %s)",
                ext_cert.id,
                assignment.id,
            )
            updates.append(CertUpdateItem(
                local_path=local_path,
                has_update=False,
            ))
            continue

        updates.append(CertUpdateItem(
            local_path=local_path,
            has_update=True,
            cert_pem=ext_cert.cert_pem,
            key_pem=key_pem,
            chain_pem=ext_cert.chain_pem,
            not_after=ext_cert.not_after,
        ))

    await _complete_rollout_item_if_ready(db, agent=agent, rollout_item=rollout_item)

    agent.cert_paths = list(checks_by_path.keys())
    db.add(agent)

    await write_audit(
        db,
        action="agent_fetch_certs",
        entity_type="agent",
        entity_id=agent.id,
        actor=agent.name,
        details={
            "paths_reported": len(body.certs),
            "paths_checked": len(all_paths),
            "paths_updated": sum(1 for u in updates if u.has_update),
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return AgentFetchCertsResponse(updates=updates)


# ---------------------------------------------------------------------------
# POST /api/agent/report-certs  (deployment confirmation)
# ---------------------------------------------------------------------------


@router.post(
    "/report-certs",
    response_model=AgentReportCertsResponse,
    summary="上报已部署证书",
    description="""
Agent 部署证书后调用此接口，上报本地已写入的证书信息。
服务端据此即时记录部署快照（Certificate 记录），无需等待下一轮 fetch-certs。

需要 `X-Agent-Token` 认证。
    """,
)
async def report_certs(
    body: AgentReportCertsRequest,
    request: Request,
    x_agent_token: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()

    if settings.dev_mode and not x_agent_token:
        result = await db.execute(
            select(Agent).where(Agent.status == AgentStatus.ACTIVE).limit(1)
        )
        agent = result.scalar_one_or_none()
        if not agent:
            raise HTTPException(status_code=404, detail="No active agent found (dev mode)")
    else:
        agent = await _resolve_agent_by_token(x_agent_token, db)

    recorded = 0
    reported_paths = list(agent.cert_paths or [])
    for item in body.certs:
        assignment_result = await db.execute(
            select(AgentCertAssignment).where(
                AgentCertAssignment.agent_id == agent.id,
                AgentCertAssignment.local_path == item.local_path,
            )
        )
        assignment = assignment_result.scalar_one_or_none()
        if assignment is None:
            continue

        ext_cert: ExternalCertificate | None = await db.get(
            ExternalCertificate, assignment.external_cert_id
        )
        if ext_cert is None or not ext_cert.is_active:
            continue

        await record_deployed_cert(
            db,
            agent_id=agent.id,
            local_path=item.local_path,
            external_cert=ext_cert,
        )
        if item.local_path not in reported_paths:
            reported_paths.append(item.local_path)
        recorded += 1

    rollout_item = await _get_active_rollout_item(db, agent_id=agent.id)
    await _complete_rollout_item_if_ready(db, agent=agent, rollout_item=rollout_item)

    if reported_paths != list(agent.cert_paths or []):
        agent.cert_paths = reported_paths
        db.add(agent)

    if recorded > 0:
        await write_audit(
            db,
            action="agent_report_certs",
            entity_type="agent",
            entity_id=agent.id,
            actor=agent.name,
            details={"reported": len(body.certs), "recorded": recorded},
            ip_address=request.client.host if request.client else None,
        )

    await db.commit()
    return AgentReportCertsResponse(recorded=recorded)
