"""FastAPI application – pure API backend, no frontend."""

import logging
import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from app.api.agent import router as agent_router
from app.api.control import router as control_router
from app.config import get_settings
from app.core.crypto import get_cert_manager, load_ca
from app.database import check_db
from app.orchestrator.rollout import advance_all_rollouts

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    ca_exists = os.path.exists(settings.ca_cert_path) and os.path.exists(settings.ca_key_path)
    if ca_exists:
        load_ca(settings.ca_cert_path, settings.ca_key_path)
        logger.info("CA loaded from %s", settings.ca_cert_path)
    elif settings.strict_ca_startup:
        raise RuntimeError(
            f"CA files not found ({settings.ca_cert_path} / {settings.ca_key_path}). "
            "Run scripts/init_ca.py first, or set STRICT_CA_STARTUP=false for dev mode."
        )
    else:
        logger.warning(
            "CA files not found (%s / %s). Running in degraded mode. "
            "Register/renew will fail until CA is loaded.",
            settings.ca_cert_path,
            settings.ca_key_path,
        )

    global _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        advance_all_rollouts,
        trigger="interval",
        seconds=settings.rollout_interval_seconds,
        id="rollout_orchestrator",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Rollout orchestrator started (interval=%ds)", settings.rollout_interval_seconds)

    yield

    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Cert Control Plane",
        description="""
## 证书生命周期管理后端

通过两组 API 管理 Agent 证书的全生命周期：

### Agent API（端口 8443，mTLS 认证）
- Agent 向控制平面注册并获取证书
- 下载证书 bundle（仅限 mTLS 端口，UI/管理侧无私钥访问）
- Agent 主动续期（提交 CSR）
- 心跳上报，查询待执行动作

### Control API（端口 443，Admin API Key 认证）
- 管理 Agent 注册信息
- 查看/撤销证书（不暴露私钥）
- 创建并管理 Rollout（批量证书轮换）
- 支持 pause / resume / rollback
- 审计日志查询

### 认证方式
- **Agent API**：nginx 在 8443 端口强制 mTLS，验证通过后注入 `X-Client-CN` 头
- **Control API**：请求头携带 `X-Admin-API-Key`
        """,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_tags=[
            {
                "name": "agent",
                "description": "**Agent API** – 运行在 8443 mTLS 端口。Agent 注册、证书下载、续期、心跳。",
            },
            {
                "name": "control / agents",
                "description": "**Control API** – Agent 管理：注册预配置、查询、删除。",
            },
            {
                "name": "control / certificates",
                "description": "**Control API** – 证书查看与撤销（只读，无私钥）。",
            },
            {
                "name": "control / rollouts",
                "description": "**Control API** – Rollout 批量证书轮换：创建、启动、暂停、恢复、回滚。",
            },
            {
                "name": "control / audit",
                "description": "**Control API** – 所有写操作的不可变审计日志。",
            },
        ],
    )

    app.include_router(agent_router)
    app.include_router(control_router)

    @app.get("/healthz", tags=["health"], summary="健康检查")
    async def healthz():
        db_ok = await check_db()
        try:
            get_cert_manager()
            ca_ok = True
        except RuntimeError:
            ca_ok = False
        healthy = db_ok and ca_ok
        return {
            "status": "ok" if healthy else "degraded",
            "db": "connected" if db_ok else "unreachable",
            "ca": "loaded" if ca_ok else "not_loaded",
        }

    return app


app = create_app()
