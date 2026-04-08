"""FastAPI application – pure API backend, no frontend."""

import logging
import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from app.api.agent import router as agent_router
from app.api.control import router as control_router
from app.api.dashboard import router as dashboard_router
from app.config import get_settings
from app.database import check_db, create_tables, dispose_engine
from app.orchestrator.rollout import advance_all_rollouts
import app.models  # noqa: F401  ensure models registered with Base

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # Auto-create tables for SQLite dev mode (production uses Alembic)
    if str(settings.database_url).startswith("sqlite"):
        await create_tables()
        logger.info("SQLite dev mode: tables auto-created")

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
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Cert Control Plane",
        description="""
## 证书分发管理后端

通过两组 API 管理 Agent 证书的全生命周期（纯分发模式，无 CA 签发）：

### Agent API
- Agent TOFU 注册（首次注册发送指纹，等待管理员审批）
- 审批后获得 Agent Token，凭 token 拉取证书和发送心跳
- 批量拉取：遍历本地证书表，与平台对比有效期，按需更新

### Control API（Admin API Key 认证）
- 管理 Agent 注册信息（查看/审批/拒绝）
- 上传外部证书（阿里云等）
- 为 Agent 分配证书（指定 local_path → external_cert 映射）
- 审计日志查询

### 认证方式
- **Agent API**：`X-Agent-Token` 请求头（审批通过后颁发）
- **Control API**：请求头携带 `X-Admin-API-Key`
        """,
        version="0.2.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_tags=[
            {
                "name": "agent",
                "description": "**Agent API** – Agent 注册、证书拉取、心跳。",
            },
            {
                "name": "control / agents",
                "description": "**Control API** – Agent 管理：注册审批、查询、删除。",
            },
            {
                "name": "control / external-certs",
                "description": "**Control API** – 外部证书管理：上传、查询、分配给 Agent。",
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

    app.include_router(dashboard_router)
    app.include_router(agent_router)
    app.include_router(control_router)

    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import HTMLResponse

    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
    
    # Mount static files *if* they exist (production mode)
    if os.path.isdir(static_dir):
        assets_dir = os.path.join(static_dir, "assets")
        if os.path.isdir(assets_dir):
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/healthz", tags=["health"], summary="健康检查")
    async def healthz():
        db_ok = await check_db()
        return {
            "status": "ok" if db_ok else "degraded",
            "db": "connected" if db_ok else "unreachable",
        }

    # SPA catch-all: serve index.html for all non-API routes (must be last)
    @app.get("/{path:path}", response_class=HTMLResponse, include_in_schema=False)
    async def spa_fallback(path: str):
        # Don't intercept API/docs routes
        if path.startswith(("api/", "docs", "redoc", "openapi.json", "healthz")):
            return HTMLResponse(status_code=404, content="Not Found")
        index_path = os.path.join(static_dir, "index.html") if os.path.isdir(static_dir) else ""
        if os.path.exists(index_path):
            with open(index_path, "r", encoding="utf-8") as f:
                return f.read()
        return HTMLResponse(
            content="Dashboard not built. Run 'npm run build' in frontend/ or use 'npm run dev' for development.",
            status_code=200,
        )

    return app


app = create_app()
