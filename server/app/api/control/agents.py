"""Control API – Agent CRUD + approval endpoints."""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.database import get_db
from app.models import (
    Agent,
    AgentCertAssignment,
    AgentStatus,
    ExternalCertificate,
)
from app.schemas import (
    AgentCreate,
    AgentDetailRead,
    AgentRead,
    PaginatedResponse,
)

from app.api.control._helpers import _actor, _ip

router = APIRouter()


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
审批通过等待中的 Agent。Agent 后续轮询注册状态时领取一次性 `agent_token`。

Agent 凭 `agent_token` 在 `X-Agent-Token` 请求头中认证，拉取证书和发送心跳。
    """,
    responses={
        200: {"description": "审批成功，等待 Agent 领取 token"},
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

    agent.agent_token_hash = None
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
    agent.agent_token_hash = None
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
