"""Rollout Orchestrator – advances batches, handles pause/resume/rollback.

CSR mode flow:
  1. Orchestrator marks rollout_items as IN_PROGRESS (= "agent should renew")
  2. Agent sees pending_action=renew in heartbeat → generates key + CSR → POST /renew
  3. /renew endpoint issues cert and marks rollout_item COMPLETED
  4. Orchestrator waits for ALL items in the current batch to finish before advancing
  5. Items stuck IN_PROGRESS beyond timeout are marked FAILED
"""

import logging
import math
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.audit import write_audit
from app.core.crypto import CertManager
from app.database import AsyncSessionLocal
from app.models import (
    Agent,
    AgentStatus,
    Certificate,
    Rollout,
    RolloutItem,
    RolloutItemStatus,
    RolloutStatus,
)
from app.registry.store import registry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rollout creation
# ---------------------------------------------------------------------------


async def create_rollout(
    db: AsyncSession,
    *,
    name: str,
    description: str | None,
    batch_size: int,
    target_filter: dict | None,
    created_by: str,
) -> Rollout:
    """Create a rollout and populate rollout_items for matched agents."""

    # Resolve target agents
    stmt = select(Agent).where(Agent.status == AgentStatus.ACTIVE)
    if target_filter:
        if prefix := target_filter.get("name_prefix"):
            stmt = stmt.where(Agent.name.startswith(prefix))
        if ids := target_filter.get("agent_ids"):
            stmt = stmt.where(Agent.id.in_([uuid.UUID(i) for i in ids]))

    result = await db.execute(stmt)
    agents = list(result.scalars().all())

    total_batches = math.ceil(len(agents) / batch_size) if agents else 0

    rollout = Rollout(
        name=name,
        description=description,
        batch_size=batch_size,
        total_batches=total_batches,
        target_filter=target_filter,
        created_by=created_by,
        status=RolloutStatus.PENDING,
    )
    db.add(rollout)
    await db.flush()  # get rollout.id

    # Create items in batch order
    for idx, agent in enumerate(agents):
        batch_number = (idx // batch_size) + 1
        # Snapshot the current cert for potential rollback
        current_cert = await registry.get_current_cert(db, agent.id)
        item = RolloutItem(
            rollout_id=rollout.id,
            agent_id=agent.id,
            status=RolloutItemStatus.PENDING,
            batch_number=batch_number,
            previous_cert_id=current_cert.id if current_cert else None,
        )
        db.add(item)

    await db.flush()
    return rollout


# ---------------------------------------------------------------------------
# Orchestrator tick – called by APScheduler
# ---------------------------------------------------------------------------


async def advance_all_rollouts() -> None:
    """Background tick: advance every RUNNING rollout.

    Each rollout gets its own independent session to prevent cross-contamination
    after commit/rollback.
    """
    # First, get the list of RUNNING rollout IDs
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Rollout.id).where(Rollout.status == RolloutStatus.RUNNING)
        )
        rollout_ids = [row[0] for row in result.all()]

    # Process each rollout in its own session
    for rollout_id in rollout_ids:
        async with AsyncSessionLocal() as db:
            try:
                rollout = await db.get(Rollout, rollout_id)
                if not rollout or rollout.status != RolloutStatus.RUNNING:
                    continue
                await _advance_rollout(db, rollout)
                await db.commit()
            except Exception as exc:
                await db.rollback()
                logger.exception("Rollout %s failed", rollout_id)
                # Mark rollout as failed in a separate clean session
                async with AsyncSessionLocal() as err_db:
                    r = await err_db.get(Rollout, rollout_id)
                    if r:
                        r.status = RolloutStatus.FAILED
                        err_db.add(r)
                        await write_audit(
                            err_db,
                            action="rollout_failed",
                            entity_type="rollout",
                            entity_id=rollout_id,
                            actor="orchestrator",
                            details={"error": str(exc)},
                        )
                        await err_db.commit()


async def _advance_rollout(db: AsyncSession, rollout: Rollout) -> None:
    """Advance one rollout (CSR mode).

    Logic:
      1. Timeout any IN_PROGRESS items that have exceeded the deadline
      2. If current batch is still in progress → wait (don't advance)
      3. If current batch is complete → advance to next batch by marking items IN_PROGRESS
      4. If all batches done → mark rollout COMPLETED
    """
    settings = get_settings()
    now = datetime.now(tz=timezone.utc)
    timeout_delta = timedelta(minutes=settings.rollout_item_timeout_minutes)

    # ----- Step 1: Timeout stale IN_PROGRESS items -----
    await _timeout_stale_items(db, rollout.id, now, timeout_delta)

    current_batch = rollout.current_batch

    # ----- Step 2: Check if current batch is still in progress -----
    if current_batch > 0:
        batch_done = await _is_batch_complete(db, rollout.id, current_batch)
        if not batch_done:
            # Still waiting for agents to finish renewal
            return

    # ----- Step 3: Advance to next batch -----
    next_batch = current_batch + 1

    if next_batch > rollout.total_batches:
        # All batches done
        rollout.status = RolloutStatus.COMPLETED
        db.add(rollout)
        await write_audit(
            db,
            action="rollout_completed",
            entity_type="rollout",
            entity_id=rollout.id,
            actor="orchestrator",
        )
        return

    # Fetch PENDING items for the next batch
    result = await db.execute(
        select(RolloutItem).where(
            RolloutItem.rollout_id == rollout.id,
            RolloutItem.batch_number == next_batch,
            RolloutItem.status == RolloutItemStatus.PENDING,
        )
    )
    items = list(result.scalars().all())

    if not items:
        # Batch is empty or already processed – skip ahead
        rollout.current_batch = next_batch
        db.add(rollout)
        return

    # Mark items as IN_PROGRESS (signal for agents via heartbeat)
    for item in items:
        item.status = RolloutItemStatus.IN_PROGRESS
        item.attempted_at = now
        db.add(item)

    rollout.current_batch = next_batch
    db.add(rollout)

    await write_audit(
        db,
        action="rollout_batch_started",
        entity_type="rollout",
        entity_id=rollout.id,
        actor="orchestrator",
        details={
            "batch": next_batch,
            "items_count": len(items),
        },
    )
    await db.flush()

    logger.info(
        "Rollout %s: started batch %d/%d (%d agents)",
        rollout.name,
        next_batch,
        rollout.total_batches,
        len(items),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _timeout_stale_items(
    db: AsyncSession,
    rollout_id: uuid.UUID,
    now: datetime,
    timeout: timedelta,
) -> None:
    """Mark IN_PROGRESS items that exceed the timeout as FAILED."""
    cutoff = now - timeout
    result = await db.execute(
        select(RolloutItem).where(
            RolloutItem.rollout_id == rollout_id,
            RolloutItem.status == RolloutItemStatus.IN_PROGRESS,
            RolloutItem.attempted_at < cutoff,
        )
    )
    stale_items = list(result.scalars().all())
    for item in stale_items:
        item.status = RolloutItemStatus.FAILED
        item.error = f"Timed out after {int(timeout.total_seconds() // 60)} minutes"
        db.add(item)
        logger.warning(
            "Rollout item %s (agent_id=%s) timed out",
            item.id,
            item.agent_id,
        )


async def _is_batch_complete(
    db: AsyncSession,
    rollout_id: uuid.UUID,
    batch_number: int,
) -> bool:
    """Return True if all items in the batch are in a terminal state."""
    terminal = (
        RolloutItemStatus.COMPLETED,
        RolloutItemStatus.FAILED,
        RolloutItemStatus.ROLLED_BACK,
    )
    result = await db.execute(
        select(func.count()).where(
            RolloutItem.rollout_id == rollout_id,
            RolloutItem.batch_number == batch_number,
            RolloutItem.status.notin_(terminal),
        )
    )
    non_terminal_count = result.scalar_one()
    return non_terminal_count == 0


# ---------------------------------------------------------------------------
# Pause / Resume / Rollback
# ---------------------------------------------------------------------------


async def pause_rollout(
    db: AsyncSession, rollout: Rollout, *, actor: str
) -> Rollout:
    if rollout.status != RolloutStatus.RUNNING:
        raise ValueError(f"Cannot pause rollout in status '{rollout.status}'")
    rollout.status = RolloutStatus.PAUSED
    db.add(rollout)
    await write_audit(
        db,
        action="rollout_paused",
        entity_type="rollout",
        entity_id=rollout.id,
        actor=actor,
    )
    return rollout


async def resume_rollout(
    db: AsyncSession, rollout: Rollout, *, actor: str
) -> Rollout:
    if rollout.status != RolloutStatus.PAUSED:
        raise ValueError(f"Cannot resume rollout in status '{rollout.status}'")
    rollout.status = RolloutStatus.RUNNING
    db.add(rollout)
    await write_audit(
        db,
        action="rollout_resumed",
        entity_type="rollout",
        entity_id=rollout.id,
        actor=actor,
    )
    return rollout


async def rollback_rollout(
    db: AsyncSession, rollout: Rollout, *, actor: str
) -> Rollout:
    """Revert all COMPLETED items to their previous cert and mark items ROLLED_BACK."""
    if rollout.status not in (
        RolloutStatus.PAUSED,
        RolloutStatus.RUNNING,
        RolloutStatus.FAILED,
        RolloutStatus.COMPLETED,
    ):
        raise ValueError(f"Cannot rollback rollout in status '{rollout.status}'")

    result = await db.execute(
        select(RolloutItem).where(
            RolloutItem.rollout_id == rollout.id,
            RolloutItem.status == RolloutItemStatus.COMPLETED,
        )
    )
    items = list(result.scalars().all())

    for item in items:
        if item.previous_cert_id:
            # Restore previous cert as current
            await db.execute(
                update(Certificate)
                .where(Certificate.agent_id == item.agent_id)
                .values(is_current=False)
            )
            await db.execute(
                update(Certificate)
                .where(Certificate.id == item.previous_cert_id)
                .values(is_current=True)
            )
            # Update agent fingerprint
            prev_cert = await db.get(Certificate, item.previous_cert_id)
            if prev_cert:
                agent = await db.get(Agent, item.agent_id)
                if agent:
                    agent.fingerprint = CertManager.fingerprint(
                        prev_cert.cert_pem.encode()
                    )
                    db.add(agent)

            await write_audit(
                db,
                action="cert_rolled_back",
                entity_type="certificate",
                entity_id=item.previous_cert_id,
                actor=actor,
                details={
                    "rollout_id": str(rollout.id),
                    "agent_id": str(item.agent_id),
                    "reverted_cert_id": str(item.new_cert_id),
                },
            )

        item.status = RolloutItemStatus.ROLLED_BACK
        db.add(item)

    rollout.status = RolloutStatus.ROLLED_BACK
    db.add(rollout)
    await write_audit(
        db,
        action="rollout_rolled_back",
        entity_type="rollout",
        entity_id=rollout.id,
        actor=actor,
        details={"items_reverted": len(items)},
    )
    await db.flush()
    return rollout
