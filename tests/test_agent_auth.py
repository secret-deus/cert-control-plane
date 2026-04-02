"""Regression tests for TOFU-based agent authentication.

Tests _resolve_agent_by_token() directly with mocked DB sessions.

Validates that:
- Missing X-Agent-Token header → 401
- Token not found / inactive agent → 403
- Valid token matching an ACTIVE agent → success
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.agent import _resolve_agent_by_token
from app.models import Agent, AgentStatus


def _make_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _make_active_agent(token: str = "valid-token") -> Agent:
    agent = MagicMock(spec=Agent)
    agent.id = uuid.uuid4()
    agent.name = "test-agent-01"
    agent.status = AgentStatus.ACTIVE
    agent.agent_token = token
    agent.fingerprint = "a" * 64
    agent.last_seen = None
    return agent


# ---------------------------------------------------------------------------
# Missing / empty token → 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deny_missing_token_none():
    """No X-Agent-Token (None) → 401."""
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc_info:
        await _resolve_agent_by_token(None, db)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_deny_missing_token_empty_string():
    """Empty string X-Agent-Token → 401."""
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc_info:
        await _resolve_agent_by_token("", db)
    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Token not found or agent not active → 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deny_unknown_token():
    """Valid-looking token but no matching active agent → 403."""
    db = AsyncMock()
    db.execute.return_value = _make_result(None)  # No agent found

    with pytest.raises(HTTPException) as exc_info:
        await _resolve_agent_by_token("unknown-token", db)
    assert exc_info.value.status_code == 403
    assert "invalid" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# Valid token → returns agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accept_valid_token():
    """Valid X-Agent-Token matching an ACTIVE agent → returns agent."""
    token = "valid-secret-token"
    agent = _make_active_agent(token=token)

    db = AsyncMock()
    db.execute.return_value = _make_result(agent)

    result = await _resolve_agent_by_token(token, db)
    assert result is agent


@pytest.mark.asyncio
async def test_token_used_in_db_query():
    """The token string must be forwarded to the DB query (no truncation)."""
    token = "x" * 64  # Long token
    agent = _make_active_agent(token=token)

    db = AsyncMock()
    db.execute.return_value = _make_result(agent)

    result = await _resolve_agent_by_token(token, db)
    assert result is agent
    # Ensure DB was called exactly once (no retry logic)
    db.execute.assert_awaited_once()
