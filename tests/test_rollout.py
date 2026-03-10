"""Tests for the Rollout Orchestrator.

Covers: batch splitting, advancing, completion, timeout, failure, rollback,
pause/resume cycle.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import (
    Agent,
    AgentStatus,
    Certificate,
    Rollout,
    RolloutItem,
    RolloutItemStatus,
    RolloutStatus,
)
from app.orchestrator.rollout import (
    _advance_rollout,
    _is_batch_complete,
    _timeout_stale_items,
    create_rollout,
    pause_rollout,
    resume_rollout,
    rollback_rollout,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent(name: str, *, status: AgentStatus = AgentStatus.ACTIVE) -> Agent:
    a = MagicMock(spec=Agent)
    a.id = uuid.uuid4()
    a.name = name
    a.status = status
    return a


def _make_rollout_item(
    rollout_id: uuid.UUID,
    agent_id: uuid.UUID,
    batch: int,
    *,
    status: RolloutItemStatus = RolloutItemStatus.PENDING,
    attempted_at: datetime | None = None,
    previous_cert_id: uuid.UUID | None = None,
    new_cert_id: uuid.UUID | None = None,
) -> RolloutItem:
    item = MagicMock(spec=RolloutItem)
    item.id = uuid.uuid4()
    item.rollout_id = rollout_id
    item.agent_id = agent_id
    item.batch_number = batch
    item.status = status
    item.attempted_at = attempted_at
    item.previous_cert_id = previous_cert_id
    item.new_cert_id = new_cert_id
    item.error = None
    return item


def _make_rollout(
    *,
    status: RolloutStatus = RolloutStatus.RUNNING,
    current_batch: int = 0,
    total_batches: int = 2,
    batch_size: int = 2,
) -> Rollout:
    r = MagicMock(spec=Rollout)
    r.id = uuid.uuid4()
    r.name = "test-rollout"
    r.status = status
    r.current_batch = current_batch
    r.total_batches = total_batches
    r.batch_size = batch_size
    return r


# ---------------------------------------------------------------------------
# Mock DB helper – builds an AsyncSession that returns prescribed query results
# ---------------------------------------------------------------------------

class MockDBBuilder:
    """Fluent builder for an AsyncSession mock with controllable query results."""

    def __init__(self):
        self._session = AsyncMock()
        self._execute_results = []

    def add_scalars_all(self, items: list) -> "MockDBBuilder":
        result = MagicMock()
        result.scalars.return_value.all.return_value = items
        self._execute_results.append(result)
        return self

    def add_scalar_one(self, value) -> "MockDBBuilder":
        result = MagicMock()
        result.scalar_one.return_value = value
        self._execute_results.append(result)
        return self

    def add_scalar_one_or_none(self, value) -> "MockDBBuilder":
        result = MagicMock()
        result.scalar_one_or_none.return_value = value
        self._execute_results.append(result)
        return self

    def build(self) -> AsyncMock:
        self._session.execute.side_effect = self._execute_results
        self._session.get = AsyncMock(return_value=None)
        return self._session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCreateRollout:
    """create_rollout should split agents into correct batch count."""

    @pytest.mark.asyncio
    async def test_create_rollout_splits_batches(self):
        agents = [_make_agent(f"agent-{i}") for i in range(5)]
        mock_cert = MagicMock(spec=Certificate)
        mock_cert.id = uuid.uuid4()

        db = MockDBBuilder()
        # 1st execute: select agents
        db.add_scalars_all(agents)
        session = db.build()

        # Mock registry.get_current_cert
        with patch("app.orchestrator.rollout.registry") as mock_reg:
            mock_reg.get_current_cert = AsyncMock(return_value=mock_cert)
            rollout = await create_rollout(
                session,
                name="test",
                description=None,
                batch_size=2,
                target_filter=None,
                created_by="admin",
            )

        assert rollout.total_batches == 3  # ceil(5/2) = 3
        assert rollout.status == RolloutStatus.PENDING


class TestAdvanceRollout:
    """_advance_rollout should manage batch progression."""

    @pytest.mark.asyncio
    async def test_advance_starts_first_batch(self):
        """When current_batch=0, advance should start batch 1."""
        rollout = _make_rollout(current_batch=0, total_batches=2)
        items = [
            _make_rollout_item(rollout.id, uuid.uuid4(), 1),
            _make_rollout_item(rollout.id, uuid.uuid4(), 1),
        ]

        db = (
            MockDBBuilder()
            .add_scalars_all([])      # timeout stale: no items
            .add_scalars_all(items)   # fetch PENDING items for batch 1
        )
        session = db.build()

        with patch("app.orchestrator.rollout.get_settings") as mock_settings:
            mock_settings.return_value.rollout_item_timeout_minutes = 10
            with patch("app.orchestrator.rollout.write_audit", new_callable=AsyncMock):
                await _advance_rollout(session, rollout)

        assert rollout.current_batch == 1
        for item in items:
            assert item.status == RolloutItemStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_advance_waits_for_batch_completion(self):
        """When current batch has non-terminal items, do nothing."""
        rollout = _make_rollout(current_batch=1, total_batches=2)

        db = (
            MockDBBuilder()
            .add_scalars_all([])   # timeout stale: no items
            .add_scalar_one(1)     # _is_batch_complete: 1 non-terminal item
        )
        session = db.build()

        with patch("app.orchestrator.rollout.get_settings") as mock_settings:
            mock_settings.return_value.rollout_item_timeout_minutes = 10
            await _advance_rollout(session, rollout)

        # Should not have advanced
        assert rollout.current_batch == 1

    @pytest.mark.asyncio
    async def test_advance_completes_rollout(self):
        """When all batches are done with no failures, mark COMPLETED."""
        rollout = _make_rollout(current_batch=2, total_batches=2)

        db = (
            MockDBBuilder()
            .add_scalars_all([])  # timeout stale
            .add_scalar_one(0)    # _is_batch_complete: 0 non-terminal
            .add_scalar_one(0)    # _count_failed_items: 0
            .add_scalar_one(0)    # _count_failed_items (final): 0
        )
        session = db.build()

        with patch("app.orchestrator.rollout.get_settings") as mock_settings:
            mock_settings.return_value.rollout_item_timeout_minutes = 10
            with patch("app.orchestrator.rollout.write_audit", new_callable=AsyncMock):
                await _advance_rollout(session, rollout)

        assert rollout.status == RolloutStatus.COMPLETED


class TestTimeout:
    """_timeout_stale_items marks timed-out IN_PROGRESS items as FAILED."""

    @pytest.mark.asyncio
    async def test_timeout_marks_items_failed(self):
        now = datetime.now(tz=timezone.utc)
        timeout = timedelta(minutes=10)
        stale_item = _make_rollout_item(
            uuid.uuid4(),
            uuid.uuid4(),
            1,
            status=RolloutItemStatus.IN_PROGRESS,
            attempted_at=now - timedelta(minutes=15),
        )

        db = MockDBBuilder().add_scalars_all([stale_item])
        session = db.build()

        await _timeout_stale_items(session, uuid.uuid4(), now, timeout)

        assert stale_item.status == RolloutItemStatus.FAILED
        assert "Timed out" in stale_item.error


class TestBatchFailure:
    """Batch failures should stop the rollout."""

    @pytest.mark.asyncio
    async def test_batch_failure_stops_rollout(self):
        rollout = _make_rollout(current_batch=1, total_batches=2)

        db = (
            MockDBBuilder()
            .add_scalars_all([])  # timeout stale
            .add_scalar_one(0)    # _is_batch_complete: 0 non-terminal (batch done)
            .add_scalar_one(1)    # _count_failed_items: 1 failure
        )
        session = db.build()

        with patch("app.orchestrator.rollout.get_settings") as mock_settings:
            mock_settings.return_value.rollout_item_timeout_minutes = 10
            with patch("app.orchestrator.rollout.write_audit", new_callable=AsyncMock):
                await _advance_rollout(session, rollout)

        assert rollout.status == RolloutStatus.FAILED


class TestRollback:
    """rollback_rollout should revert COMPLETED and handle IN_PROGRESS items."""

    @pytest.mark.asyncio
    async def test_rollback_reverts_completed_items(self):
        rollout = _make_rollout(status=RolloutStatus.PAUSED)
        prev_cert_id = uuid.uuid4()
        new_cert_id = uuid.uuid4()
        agent_id = uuid.uuid4()

        completed_item = _make_rollout_item(
            rollout.id, agent_id, 1,
            status=RolloutItemStatus.COMPLETED,
            previous_cert_id=prev_cert_id,
            new_cert_id=new_cert_id,
        )

        prev_cert = MagicMock(spec=Certificate)
        prev_cert.cert_pem = "-----BEGIN CERTIFICATE-----\nMOCK\n-----END CERTIFICATE-----"

        agent = _make_agent("test-agent")

        session = AsyncMock()

        # First execute returns items, subsequent executes (updates) return default
        first_call = True

        async def mock_execute(*args, **kwargs):
            nonlocal first_call
            if first_call:
                first_call = False
                result = MagicMock()
                result.scalars.return_value.all.return_value = [completed_item]
                return result
            return MagicMock()

        session.execute = AsyncMock(side_effect=mock_execute)
        session.get = AsyncMock(side_effect=lambda model, pk: {
            prev_cert_id: prev_cert,
            agent_id: agent,
        }.get(pk))

        with patch("app.orchestrator.rollout.write_audit", new_callable=AsyncMock), \
             patch("app.orchestrator.rollout.CertManager") as mock_cm:
            mock_cm.fingerprint.return_value = "mock-fingerprint"
            result = await rollback_rollout(session, rollout, actor="admin")

        assert result.status == RolloutStatus.ROLLED_BACK
        assert completed_item.status == RolloutItemStatus.ROLLED_BACK

    @pytest.mark.asyncio
    async def test_rollback_handles_in_progress_items(self):
        rollout = _make_rollout(status=RolloutStatus.RUNNING)
        agent_id = uuid.uuid4()

        in_progress_item = _make_rollout_item(
            rollout.id, agent_id, 1,
            status=RolloutItemStatus.IN_PROGRESS,
        )

        db = MockDBBuilder().add_scalars_all([in_progress_item])
        session = db.build()

        with patch("app.orchestrator.rollout.write_audit", new_callable=AsyncMock):
            result = await rollback_rollout(session, rollout, actor="admin")

        assert result.status == RolloutStatus.ROLLED_BACK
        assert in_progress_item.status == RolloutItemStatus.ROLLED_BACK


class TestPauseResume:
    """pause_rollout / resume_rollout cycle."""

    @pytest.mark.asyncio
    async def test_pause_resume_cycle(self):
        rollout = _make_rollout(status=RolloutStatus.RUNNING)
        db = AsyncMock()

        with patch("app.orchestrator.rollout.write_audit", new_callable=AsyncMock):
            paused = await pause_rollout(db, rollout, actor="admin")
            assert paused.status == RolloutStatus.PAUSED

            resumed = await resume_rollout(db, rollout, actor="admin")
            assert resumed.status == RolloutStatus.RUNNING
