"""Agent API – endpoints called by agents over mTLS (port 8443).

Authentication:
  - /register  : one-time bootstrap_token in request body
  - other endpoints: mTLS client cert → X-Client-CN header injected by nginx
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.audit import write_audit
from app.database import get_db
from app.models import Agent, AgentStatus, RolloutItem, RolloutItemStatus
from app.registry.store import registry
from app.schemas import (
    AgentRegisterRequest,
    AgentRegisterResponse,
    AgentRenewRequest,
    AgentRenewResponse,
    HeartbeatRequest,
    HeartbeatResponse,
)

router = APIRouter(prefix="/api/agent", tags=["agent"])


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


async def _resolve_agent_by_cn(x_client_cn: str | None, db: AsyncSession) -> Agent:
    """Resolve nginx-injected X-Client-CN to an active Agent row."""
    if not x_client_cn:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="mTLS client certificate required (X-Client-CN header missing)",
        )
    result = await db.execute(
        select(Agent).where(
            Agent.name == x_client_cn,
            Agent.status == AgentStatus.ACTIVE,
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"No active agent for CN '{x_client_cn}'",
        )
    return agent


# ---------------------------------------------------------------------------
# POST /api/agent/register
# ---------------------------------------------------------------------------


@router.post(
    "/register",
    response_model=AgentRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Agent 注册",
    description="""
Agent 首次注册，使用控制平面预生成的一次性 **bootstrap_token** 完成身份验证。

**流程：**
1. 运维人员通过 `POST /api/control/agents` 预配置 Agent，获得 `bootstrap_token`
2. Agent 本地生成 RSA 私钥和 CSR（私钥**永远不离开 Agent**）
3. Agent 调用此接口提交 `bootstrap_token` + CSR
4. 控制平面签发证书并返回 `cert_pem` + `chain_pem`
5. `bootstrap_token` 立即作废（一次性）
6. 后续所有请求使用 mTLS（凭此证书）

**注意：** 此接口部署在 8443 mTLS 端口，首次注册时无需客户端证书（bootstrap 阶段）。
    """,
    responses={
        201: {"description": "注册成功，返回证书 PEM"},
        401: {"description": "bootstrap_token 无效或已使用"},
    },
)
async def register_agent(
    body: AgentRegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Agent).where(
            Agent.bootstrap_token == body.bootstrap_token,
            Agent.status == AgentStatus.PENDING,
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired bootstrap token",
        )

    # Check token expiry
    settings = get_settings()
    if agent.bootstrap_token_created_at:
        expire_at = agent.bootstrap_token_created_at + timedelta(
            hours=settings.bootstrap_token_expire_hours
        )
        if datetime.now(tz=timezone.utc) > expire_at:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bootstrap token has expired",
            )

    try:
        cert = await registry.issue_from_csr(db, agent=agent, csr_pem=body.csr_pem)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    agent.bootstrap_token = None  # Consume token
    db.add(agent)

    await write_audit(
        db,
        action="agent_registered",
        entity_type="agent",
        entity_id=agent.id,
        actor=agent.name,
        details={"serial": cert.serial},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(cert)

    return AgentRegisterResponse(
        cert_pem=cert.cert_pem,
        chain_pem=cert.chain_pem,
        agent_id=agent.id,
    )


# ---------------------------------------------------------------------------
# GET /api/agent/bundle
# ---------------------------------------------------------------------------


@router.get(
    "/bundle",
    summary="下载证书 Bundle",
    description="""
下载当前 Agent 的证书 Bundle（PEM 格式，证书 + CA 链拼接）。

**安全约束：**
- 此端点**仅**开放在 8443 mTLS 端口，必须持有有效客户端证书才能访问
- nginx 在 443 控制端口上对此路径返回 `403`，**运维 UI 无法访问**
- 若证书由控制平面服务端生成（非 CSR 流程），返回内容包含私钥；CSR 流程下仅返回证书链（私钥在 Agent 本地）

**响应格式：** `application/x-pem-file`，多段 PEM 拼接（cert → key（如有）→ chain）
    """,
    response_class=PlainTextResponse,
    responses={
        200: {"description": "PEM bundle 文件", "content": {"application/x-pem-file": {}}},
        401: {"description": "缺少 mTLS 客户端证书"},
        403: {"description": "Agent 未激活或 CN 不匹配"},
        404: {"description": "当前无有效证书"},
    },
)
async def download_bundle(
    x_client_cn: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    agent = await _resolve_agent_by_cn(x_client_cn, db)
    cert = await registry.get_current_cert(db, agent.id)
    if not cert:
        raise HTTPException(status_code=404, detail="No active certificate found")

    bundle = registry.build_bundle(cert, include_key=True)
    parts = [bundle["cert_pem"]]
    if bundle["key_pem"]:
        parts.append(bundle["key_pem"])
    if bundle["chain_pem"]:
        parts.append(bundle["chain_pem"])

    return PlainTextResponse(
        content="\n".join(p.strip() for p in parts),
        media_type="application/x-pem-file",
        headers={"Content-Disposition": f'attachment; filename="{agent.name}.pem"'},
    )


# ---------------------------------------------------------------------------
# POST /api/agent/renew
# ---------------------------------------------------------------------------


@router.post(
    "/renew",
    response_model=AgentRenewResponse,
    summary="证书续期",
    description="""
Agent 主动发起证书续期，提交新 CSR（Agent 重新生成私钥）。

**适用场景：**
- 控制平面通过 Rollout 批次分配了续期任务（heartbeat 返回 `pending_action: "renew"`）
- Agent 主动发起的定期轮换

**流程：**
1. Agent 生成新的私钥 + CSR（旧私钥可以立即丢弃）
2. 提交 CSR 到此接口
3. 控制平面签发新证书，旧证书自动标记为 `is_current=false`
4. 若当前有关联的 Rollout item，自动标记为 `completed`
    """,
    responses={
        200: {"description": "新证书签发成功"},
        401: {"description": "缺少 mTLS 客户端证书"},
        403: {"description": "Agent 未激活"},
    },
)
async def renew_cert(
    body: AgentRenewRequest,
    request: Request,
    x_client_cn: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    agent = await _resolve_agent_by_cn(x_client_cn, db)
    try:
        cert = await registry.issue_from_csr(db, agent=agent, csr_pem=body.csr_pem)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Mark any in-progress rollout item as completed
    result = await db.execute(
        select(RolloutItem).where(
            RolloutItem.agent_id == agent.id,
            RolloutItem.status == RolloutItemStatus.IN_PROGRESS,
        )
    )
    item = result.scalar_one_or_none()
    if item:
        item.new_cert_id = cert.id
        item.status = RolloutItemStatus.COMPLETED
        item.completed_at = datetime.now(tz=timezone.utc)
        db.add(item)

    await write_audit(
        db,
        action="cert_renewed",
        entity_type="certificate",
        entity_id=cert.id,
        actor=agent.name,
        details={"serial": cert.serial},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(cert)

    return AgentRenewResponse(
        cert_pem=cert.cert_pem,
        chain_pem=cert.chain_pem,
        serial=cert.serial,
    )


# ---------------------------------------------------------------------------
# POST /api/agent/heartbeat
# ---------------------------------------------------------------------------


@router.post(
    "/heartbeat",
    response_model=HeartbeatResponse,
    summary="心跳上报",
    description="""
Agent 定期调用，更新 `last_seen` 时间戳并查询是否有待执行的证书操作。

**响应字段 `pending_action`：**
- `null` – 无待操作
- `"renew"` – 控制平面已为此 Agent 分配了续期任务，Agent 应调用 `POST /api/agent/renew`

建议 Agent 每 30~60 秒调用一次。
    """,
    responses={
        200: {"description": "心跳确认，包含待操作指令"},
        401: {"description": "缺少 mTLS 客户端证书"},
    },
)
async def heartbeat(
    body: HeartbeatRequest,
    x_client_cn: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    agent = await _resolve_agent_by_cn(x_client_cn, db)
    agent.last_seen = datetime.now(tz=timezone.utc)
    db.add(agent)

    result = await db.execute(
        select(RolloutItem).where(
            RolloutItem.agent_id == agent.id,
            RolloutItem.status == RolloutItemStatus.IN_PROGRESS,
        )
    )
    pending = result.scalar_one_or_none()

    await db.commit()
    return HeartbeatResponse(
        acknowledged=True,
        pending_action="renew" if pending else None,
    )
