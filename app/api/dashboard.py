"""Dashboard API – aggregations for the control plane web UI."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_admin_key
from app.database import get_db
from app.models import Agent, AgentStatus, AuditLog, Certificate, Rollout, RolloutStatus

router = APIRouter(
    prefix="/api/control/dashboard",
    dependencies=[Depends(verify_admin_key)],
    tags=["control / dashboard"],
)


@router.get("/summary", summary="Dashboard global summary stats")
async def get_summary(db: AsyncSession = Depends(get_db)):
    """Aggregate stats for the top cards on the dashboard."""
    # Agent stats
    agents_total = (await db.execute(select(func.count()).select_from(Agent))).scalar_one()
    agents_active = (
        await db.execute(
            select(func.count())
            .select_from(Agent)
            .where(Agent.status == AgentStatus.ACTIVE)
        )
    ).scalar_one()
    
    # Cert stats
    certs_total = (
        await db.execute(
            select(func.count())
            .select_from(Certificate)
            .where(Certificate.is_current.is_(True), Certificate.revoked_at.is_(None))
        )
    ).scalar_one()
    
    soon = datetime.now(tz=timezone.utc) + timedelta(days=30)
    certs_expiring_soon = (
        await db.execute(
            select(func.count())
            .select_from(Certificate)
            .where(
                Certificate.is_current.is_(True),
                Certificate.revoked_at.is_(None),
                Certificate.not_after <= soon,
            )
        )
    ).scalar_one()

    # Rollout stats
    rollouts_active = (
        await db.execute(
            select(func.count())
            .select_from(Rollout)
            .where(Rollout.status == RolloutStatus.RUNNING)
        )
    ).scalar_one()

    return {
        "agents": {"total": agents_total, "active": agents_active},
        "certificates": {"total_active": certs_total, "expiring_soon": certs_expiring_soon},
        "rollouts": {"running": rollouts_active},
    }


@router.get("/agents-health", summary="Agent liveness list")
async def get_agents_health(db: AsyncSession = Depends(get_db)):
    """List of all agents with their last_seen and current cert info for the health table."""
    result = await db.execute(
        select(Agent, Certificate)
        .outerjoin(
            Certificate, 
            (Certificate.agent_id == Agent.id) & (Certificate.is_current.is_(True))
        )
        .order_by(Agent.name)
    )
    
    health_list = []
    now = datetime.now(tz=timezone.utc)
    
    for agent, cert in result.all():
        # Determine liveness based on last_seen
        liveness = "offline"
        if agent.last_seen:
            diff = (now - agent.last_seen).total_seconds()
            if diff < 90:  # 1.5x heartbeat interval (30s)
                liveness = "online"
            elif diff < 300:
                liveness = "delayed"
                
        health_list.append({
            "id": agent.id,
            "name": agent.name,
            "status": agent.status,
            "liveness": liveness,
            "last_seen": agent.last_seen,
            "cert_expires_at": cert.not_after if cert else None,
            "cert_revoked_at": cert.revoked_at if cert else None,
        })
        
    return health_list


@router.get("/certs-expiry", summary="Upcoming certificate expirations")
async def get_certs_expiry(db: AsyncSession = Depends(get_db)):
    """List of certificates expiring within the next 30 days, sorted by nearest first."""
    soon = datetime.now(tz=timezone.utc) + timedelta(days=30)
    result = await db.execute(
        select(Certificate)
        .where(
            Certificate.is_current.is_(True),
            Certificate.revoked_at.is_(None),
            Certificate.not_after <= soon,
        )
        .order_by(Certificate.not_after.asc())
        .limit(20)
    )
    
    return [
        {
            "id": c.id,
            "agent_id": c.agent_id,
            "subject_cn": c.subject_cn,
            "serial_hex": c.serial_hex,
            "not_after": c.not_after,
        }
        for c in result.scalars().all()
    ]


@router.get("/events", summary="Recent audit events timeline")
async def get_events_timeline(db: AsyncSession = Depends(get_db)):
    """Latest 50 audit log events for the timeline component."""
    result = await db.execute(
        select(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(50)
    )
    
    return [
        {
            "id": log.id,
            "action": log.action,
            "entity_type": log.entity_type,
            "actor": log.actor,
            "created_at": log.created_at,
            "details": log.details,
        }
        for log in result.scalars().all()
    ]
