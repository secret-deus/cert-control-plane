"""Certificate registry – minimal helpers kept for rollout compatibility."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Certificate


async def get_current_cert(
    db: AsyncSession, agent_id: uuid.UUID
) -> Certificate | None:
    """Return the active non-revoked certificate for an agent."""
    result = await db.execute(
        select(Certificate).where(
            Certificate.agent_id == agent_id,
            Certificate.is_current.is_(True),
            Certificate.revoked_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def revoke_cert(db: AsyncSession, cert: Certificate) -> Certificate:
    """Mark a certificate as revoked."""
    cert.revoked_at = datetime.now(tz=timezone.utc)
    cert.is_current = False
    db.add(cert)
    await db.flush()
    return cert
