"""Control API – Audit log query endpoint."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AuditLog
from app.schemas import AuditLogRead, PaginatedResponse

router = APIRouter()


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
