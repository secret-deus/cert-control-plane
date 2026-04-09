"""Certificate registry – minimal helpers kept for rollout compatibility."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Certificate, ExternalCertificate


async def get_current_cert(
    db: AsyncSession,
    agent_id: uuid.UUID,
    *,
    local_path: str | None = None,
) -> Certificate | None:
    """Return the active non-revoked certificate for an agent."""
    stmt = select(Certificate).where(
        Certificate.agent_id == agent_id,
        Certificate.is_current.is_(True),
        Certificate.revoked_at.is_(None),
    )
    if local_path is not None:
        stmt = stmt.where(Certificate.local_path == local_path)
    stmt = stmt.order_by(Certificate.created_at.desc()).limit(1)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def revoke_cert(db: AsyncSession, cert: Certificate) -> Certificate:
    """Mark a certificate as revoked."""
    cert.revoked_at = datetime.now(tz=timezone.utc)
    cert.is_current = False
    db.add(cert)
    await db.flush()
    return cert


async def record_deployed_cert(
    db: AsyncSession,
    *,
    agent_id: uuid.UUID,
    local_path: str,
    external_cert: ExternalCertificate,
) -> Certificate:
    """Persist the currently deployed certificate snapshot for an agent path."""
    current = await get_current_cert(db, agent_id, local_path=local_path)
    if (
        current
        and current.external_cert_id == external_cert.id
        and current.serial_hex == external_cert.serial_hex
        and current.not_after == external_cert.not_after
    ):
        await db.execute(
            update(Certificate)
            .where(
                Certificate.agent_id == agent_id,
                Certificate.local_path == local_path,
                Certificate.is_current.is_(True),
                Certificate.id != current.id,
            )
            .values(is_current=False, revoked_at=datetime.now(tz=timezone.utc))
        )
        return current

    await db.execute(
        update(Certificate)
        .where(
            Certificate.agent_id == agent_id,
            Certificate.local_path == local_path,
            Certificate.is_current.is_(True),
        )
        .values(is_current=False, revoked_at=datetime.now(tz=timezone.utc))
    )

    snapshot = Certificate(
        agent_id=agent_id,
        external_cert_id=external_cert.id,
        local_path=local_path,
        serial_hex=external_cert.serial_hex,
        subject_cn=external_cert.subject_cn,
        not_before=external_cert.not_before,
        not_after=external_cert.not_after,
        cert_pem=external_cert.cert_pem,
        chain_pem=external_cert.chain_pem,
        is_current=True,
    )
    db.add(snapshot)
    await db.flush()
    return snapshot
