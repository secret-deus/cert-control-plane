"""Control API – admin-facing endpoints (X-Admin-API-Key auth)."""
from fastapi import APIRouter, Depends

from app.core.security import verify_admin_key

from app.api.control.agents import router as agents_router
from app.api.control.external_certs import router as external_certs_router
from app.api.control.assignments import router as assignments_router
from app.api.control.rollouts import router as rollouts_router
from app.api.control.kubernetes import router as kubernetes_router
from app.api.control.audit import router as audit_router

router = APIRouter(
    prefix="/api/control",
    dependencies=[Depends(verify_admin_key)],
)
router.include_router(agents_router)
router.include_router(external_certs_router)
router.include_router(assignments_router)
router.include_router(rollouts_router)
router.include_router(kubernetes_router)
router.include_router(audit_router)
