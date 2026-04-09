"""Audit log helpers – every write operation must call write_audit()."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


async def write_audit(
    db: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: str | uuid.UUID | None = None,
    actor: str,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else None,
        actor=actor,
        details=details,
        ip_address=ip_address,
    )
    db.add(entry)
    # Flush so the entry gets an ID; caller is responsible for commit.
    await db.flush()
    return entry
