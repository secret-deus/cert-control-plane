"""Control API – admin-facing endpoints (port 443, X-Admin-API-Key auth)."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import write_audit
from app.core.security import generate_bootstrap_token, verify_admin_key
from app.database import get_db
from app.models import Agent, AgentStatus, AuditLog, Certificate, Rollout, RolloutStatus
from app.orchestrator.rollout import (
    create_rollout,
    pause_rollout,
    resume_rollout,
    rollback_rollout,
)
from app.schemas import (
    AgentCreate,
    AgentDetail,
    AgentRead,
    AuditLogRead,
    CertRead,
    CertSummary,
    PaginatedResponse,
    RolloutCreate,
    RolloutDetail,
    RolloutRead,
)

router = APIRouter(
    prefix="/api/control",
    dependencies=[Depends(verify_admin_key)],
)


# ===========================================================================
# Agents
# ===========================================================================


@router.post(
    "/agents",
    response_model=AgentDetail,
    status_code=status.HTTP_201_CREATED,
    tags=["control / agents"],
    summary="预注册 Agent",
    description="""
在控制平面预配置一个 Agent 条目，生成**一次性 bootstrap_token**。

**返回值中的 `bootstrap_token` 仅在此响应中出现一次**，后续查询不再返回。
请将 token 安全传递给对应的 Agent（如通过密钥管理系统或首次部署脚本）。

Agent 收到 token 后调用 `POST /api/agent/register` 完成注册，token 即作废。
    """,
    responses={
        201: {"description": "Agent 预注册成功，返回一次性 bootstrap_token"},
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

    token = generate_bootstrap_token()
    agent = Agent(
        name=body.name,
        description=body.description,
        bootstrap_token=token,
        bootstrap_token_created_at=datetime.now(tz=timezone.utc),
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
    description="分页查询所有 Agent，可按 `status` 过滤（pending/active/revoked/expired）。",
)
async def list_agents(
    status_filter: AgentStatus | None = Query(None, alias="status", description="过滤 Agent 状态"),
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
    description="删除 Agent 及其所有关联证书（级联删除）。",
    responses={
        204: {"description": "删除成功"},
        404: {"description": "Agent 不存在"},
    },
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
    "/agents/{agent_id}/reset-token",
    response_model=AgentDetail,
    tags=["control / agents"],
    summary="重置 Bootstrap Token",
    description="""
为指定 Agent 生成新的一次性 **bootstrap_token**，用于节点重新注册。

**适用场景：**
- Agent 证书过期或被吊销后需要重新注册
- Agent 节点重装系统，本地状态丢失
- mTLS 认证持续失败，需要重新建立信任

**操作效果：**
1. 生成新的 bootstrap_token（旧 token 作废）
2. 将 Agent 状态重置为 `pending`
3. Agent 使用新 token 重新走注册流程

**注意：** 重置后 Agent 需要重新配置 `CERT_AGENT_BOOTSTRAP_TOKEN` 并重启。
    """,
    responses={
        200: {"description": "Token 重置成功，返回新 token（仅此一次）"},
        404: {"description": "Agent 不存在"},
    },
)
async def reset_agent_token(
    agent_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    new_token = generate_bootstrap_token()
    agent.bootstrap_token = new_token
    agent.bootstrap_token_created_at = datetime.now(tz=timezone.utc)
    agent.status = AgentStatus.PENDING
    db.add(agent)

    await write_audit(
        db,
        action="agent_token_reset",
        entity_type="agent",
        entity_id=agent_id,
        actor=_actor(request),
        ip_address=_ip(request),
    )
    await db.commit()
    await db.refresh(agent)
    return agent


# ===========================================================================
# Certificates
# ===========================================================================


@router.get(
    "/agents/{agent_id}/certs",
    response_model=list[CertSummary],
    tags=["control / certificates"],
    summary="Agent 证书历史",
    description="""
查询指定 Agent 的所有证书摘要（按时间倒序，不含 PEM 正文）。

使用 `GET /certs/{cert_id}` 获取单张证书的完整 PEM。

**私钥字段不存在于任何响应中**——`key_pem_encrypted` 字段在数据库中加密存储，
此接口及所有控制侧接口均不返回私钥。私钥只能由 Agent 通过 mTLS 端口（8443）下载。
    """,
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


@router.post(
    "/certs/{cert_id}/revoke",
    response_model=CertRead,
    tags=["control / certificates"],
    summary="撤销证书",
    description="""
将指定证书标记为已撤销（设置 `revoked_at`，`is_current` 置为 `false`）。

撤销后 Agent 下次心跳会收到 `pending_action: "renew"` 通知（如有 Rollout item）。
目前不生成 CRL / OCSP，需要结合 Rollout 完成实际轮换。
    """,
    responses={
        200: {"description": "撤销成功"},
        404: {"description": "证书不存在"},
        409: {"description": "证书已撤销"},
    },
)
async def revoke_cert(
    cert_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    from app.registry.store import registry

    cert = await db.get(Certificate, cert_id)
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    if cert.revoked_at:
        raise HTTPException(status_code=409, detail="Certificate already revoked")

    cert = await registry.revoke(db, cert)
    await write_audit(
        db,
        action="cert_revoked",
        entity_type="certificate",
        entity_id=cert_id,
        actor=_actor(request),
        ip_address=_ip(request),
    )
    await db.commit()
    await db.refresh(cert)
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
    description="""
创建一次批量证书轮换任务，系统自动按 `target_filter` 匹配 Agent 并分批。

**`target_filter` 示例：**
```json
{"name_prefix": "prod-"}         // 匹配所有名称以 prod- 开头的 Agent
{"agent_ids": ["uuid1","uuid2"]} // 指定 Agent
null                              // 所有 active Agent
```

创建后状态为 `pending`，需调用 `POST /rollouts/{id}/start` 启动。
    """,
    responses={201: {"description": "Rollout 创建成功，状态为 pending"}},
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
    description="分页查询，可按 `status` 过滤（pending/running/paused/completed/failed/rolled_back）。",
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
    summary="Rollout 详情（含每个 Agent 的执行状态）",
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
    description="将 Rollout 状态从 `pending` 切换为 `running`，Orchestrator 开始按批次推进。",
    responses={
        200: {"description": "启动成功"},
        404: {"description": "Rollout 不存在"},
        409: {"description": "Rollout 不在 pending 状态"},
    },
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
    description="""
暂停正在运行的 Rollout。Orchestrator 停止推进下一批次，已在执行的批次不受影响。

可通过 `POST .../resume` 恢复，或 `POST .../rollback` 回滚。
    """,
    responses={
        200: {"description": "暂停成功"},
        409: {"description": "Rollout 不在 running 状态"},
    },
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
    description="将已暂停的 Rollout 恢复为 `running`，Orchestrator 继续从下一批次推进。",
    responses={
        200: {"description": "恢复成功"},
        409: {"description": "Rollout 不在 paused 状态"},
    },
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
    description="""
将所有已完成的 Rollout item 恢复到轮换**之前**的证书。

**操作内容：**
- 对每个 `completed` 状态的 item，将 Agent 的 `is_current` 恢复为 `previous_cert_id` 指向的证书
- 更新 Agent 的 `fingerprint`
- 所有 item 状态置为 `rolled_back`
- Rollout 状态置为 `rolled_back`

**支持的前置状态：** `paused` / `running` / `failed` / `completed`
    """,
    responses={
        200: {"description": "回滚成功"},
        409: {"description": "当前状态不支持回滚"},
    },
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

**可过滤字段：**
- `entity_type`：`agent` / `certificate` / `rollout`
- `entity_id`：具体资源的 UUID

**覆盖的操作：**
`agent_created` / `agent_registered` / `agent_deleted` / `agent_token_reset` /
`cert_renewed` / `cert_revoked` / `cert_rolled_back` /
`rollout_created` / `rollout_started` / `rollout_batch_started` /
`rollout_paused` / `rollout_resumed` /
`rollout_completed` / `rollout_failed` / `rollout_rolled_back`
    """,
)
async def list_audit_logs(
    entity_type: str | None = Query(None, description="实体类型过滤"),
    entity_id: str | None = Query(None, description="实体 UUID 过滤"),
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
    """Extract actor identity from request (X-Actor header or fallback to 'admin')."""
    return request.headers.get("X-Actor", "admin")


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None
