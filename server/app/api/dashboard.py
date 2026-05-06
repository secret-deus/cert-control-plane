"""Dashboard API – aggregations for the control plane web UI."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_admin_key
from app.database import get_db
from app.models import Agent, AgentStatus, AuditLog, Certificate, ExternalCertificate, Rollout, RolloutStatus
from app.schemas import AgentHealth, AuditEvent, CertExpiry, DashboardSummary

router = APIRouter(
    prefix="/api/control/dashboard",
    dependencies=[Depends(verify_admin_key)],
    tags=["control / dashboard"],
)


@router.get("/summary", summary="Dashboard global summary stats", response_model=DashboardSummary)
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
    agents_pending = (
        await db.execute(
            select(func.count())
            .select_from(Agent)
            .where(Agent.status == AgentStatus.PENDING_APPROVAL)
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
        "agents": {"total": agents_total, "active": agents_active, "pending_approval": agents_pending},
        "certificates": {"total_active": certs_total, "expiring_soon": certs_expiring_soon},
        "rollouts": {"running": rollouts_active},
    }


@router.get("/agents-health", summary="Agent liveness list", response_model=list[AgentHealth])
async def get_agents_health(db: AsyncSession = Depends(get_db)):
    """List of all agents with their last_seen and current cert info for the health table."""
    agents_result = await db.execute(
        select(Agent).order_by(Agent.name)
    )
    agents = agents_result.scalars().all()

    now = datetime.now(tz=timezone.utc)
    health_list = []

    for agent in agents:
        liveness = "offline"
        if agent.last_seen:
            diff = (now - agent.last_seen).total_seconds()
            if diff < 90:
                liveness = "online"
            elif diff < 300:
                liveness = "delayed"

        cert_result = await db.execute(
            select(Certificate)
            .where(
                Certificate.agent_id == agent.id,
                Certificate.is_current.is_(True),
                Certificate.revoked_at.is_(None),
            )
            .order_by(Certificate.not_after.asc())
            .limit(1)
        )
        earliest_cert = cert_result.scalar_one_or_none()

        health_list.append({
            "id": agent.id,
            "name": agent.name,
            "status": agent.status,
            "liveness": liveness,
            "last_seen": agent.last_seen,
            "cert_expires_at": earliest_cert.not_after if earliest_cert else None,
            "cert_revoked_at": earliest_cert.revoked_at if earliest_cert else None,
        })

    return health_list


@router.get("/certs-expiry", summary="Upcoming certificate expirations", response_model=list[CertExpiry])
async def get_certs_expiry(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
):
    """List of certificates expiring within the next N days, sorted by nearest first."""
    soon = datetime.now(tz=timezone.utc) + timedelta(days=days)
    result = await db.execute(
        select(Certificate)
        .where(
            Certificate.is_current.is_(True),
            Certificate.revoked_at.is_(None),
            Certificate.not_after <= soon,
        )
        .order_by(Certificate.not_after.asc())
        .limit(50)
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


@router.get(
    "/external-certs-expiry",
    summary="外部证书过期监控",
    response_model=list[dict],
)
async def get_external_certs_expiry(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
):
    """
    监控外部证书（阿里云等）的过期情况。
    返回 N 天内即将到期的外部证书，包含过期状态分级。
    """
    now = datetime.now(tz=timezone.utc)
    soon = now + timedelta(days=days)

    result = await db.execute(
        select(ExternalCertificate)
        .where(
            ExternalCertificate.is_active.is_(True),
            ExternalCertificate.not_after <= soon,
        )
        .order_by(ExternalCertificate.not_after.asc())
    )

    certs = result.scalars().all()
    items = []

    for cert in certs:
        days_remaining = (cert.not_after - now).days
        if days_remaining < 0:
            urgency = "expired"
        elif days_remaining <= 7:
            urgency = "critical"
        elif days_remaining <= 14:
            urgency = "warning"
        else:
            urgency = "notice"

        items.append({
            "id": str(cert.id),
            "name": cert.name,
            "subject_cn": cert.subject_cn,
            "serial_hex": cert.serial_hex,
            "not_after": cert.not_after.isoformat(),
            "days_remaining": days_remaining,
            "provider": cert.provider,
            "urgency": urgency,
        })

    return items


@router.get("/events", summary="Recent audit events timeline", response_model=list[AuditEvent])
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


@router.get(
    "/cert-alerts",
    summary="证书过期告警概览",
    response_model=dict,
)
async def get_cert_alerts(db: AsyncSession = Depends(get_db)):
    """
    获取证书过期告警概览，包括外部证书和 Agent 证书。
    返回分级统计：expired, critical, warning, notice
    """
    now = datetime.now(tz=timezone.utc)

    # Define time thresholds
    notice_threshold = now + timedelta(days=30)

    # Query external certificates
    ext_result = await db.execute(
        select(ExternalCertificate)
        .where(
            ExternalCertificate.is_active.is_(True),
            ExternalCertificate.not_after <= notice_threshold,
        )
    )
    ext_certs = ext_result.scalars().all()

    # Query agent certificates
    agent_result = await db.execute(
        select(Certificate)
        .where(
            Certificate.is_current.is_(True),
            Certificate.revoked_at.is_(None),
            Certificate.not_after <= notice_threshold,
        )
    )
    agent_certs = agent_result.scalars().all()

    # Categorize external certs
    ext_alerts = {"expired": [], "critical": [], "warning": [], "notice": []}
    for cert in ext_certs:
        days_remaining = (cert.not_after - now).days
        alert = {
            "id": str(cert.id),
            "name": cert.name,
            "subject_cn": cert.subject_cn,
            "serial_hex": cert.serial_hex,
            "not_after": cert.not_after.isoformat(),
            "days_remaining": days_remaining,
            "provider": cert.provider,
            "type": "external",
        }
        if days_remaining < 0:
            ext_alerts["expired"].append(alert)
        elif days_remaining <= 7:
            ext_alerts["critical"].append(alert)
        elif days_remaining <= 14:
            ext_alerts["warning"].append(alert)
        else:
            ext_alerts["notice"].append(alert)

    # Categorize agent certs
    agent_alerts = {"expired": [], "critical": [], "warning": [], "notice": []}
    for cert in agent_certs:
        days_remaining = (cert.not_after - now).days
        alert = {
            "id": str(cert.id),
            "agent_id": str(cert.agent_id),
            "subject_cn": cert.subject_cn,
            "serial_hex": cert.serial_hex,
            "not_after": cert.not_after.isoformat(),
            "days_remaining": days_remaining,
            "type": "agent",
        }
        if days_remaining < 0:
            agent_alerts["expired"].append(alert)
        elif days_remaining <= 7:
            agent_alerts["critical"].append(alert)
        elif days_remaining <= 14:
            agent_alerts["warning"].append(alert)
        else:
            agent_alerts["notice"].append(alert)

    return {
        "summary": {
            "external": {
                "total_alerts": len(ext_certs),
                "expired": len(ext_alerts["expired"]),
                "critical": len(ext_alerts["critical"]),
                "warning": len(ext_alerts["warning"]),
                "notice": len(ext_alerts["notice"]),
            },
            "agent": {
                "total_alerts": len(agent_certs),
                "expired": len(agent_alerts["expired"]),
                "critical": len(agent_alerts["critical"]),
                "warning": len(agent_alerts["warning"]),
                "notice": len(agent_alerts["notice"]),
            },
        },
        "external_certs": ext_alerts,
        "agent_certs": agent_alerts,
        "generated_at": now.isoformat(),
    }
