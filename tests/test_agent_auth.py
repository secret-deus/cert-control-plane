"""Regression tests for TASK-002/003: fail-closed agent auth.

Tests _resolve_agent() directly with mocked DB sessions.
Validates that:
- Missing X-Client-CN → 401 (DENY_MISSING_CN)
- Missing X-Client-Serial → 401 (DENY_MISSING_SERIAL)
- Agent not active → 403 (DENY_AGENT_NOT_ACTIVE)
- No current cert → 403 (DENY_NO_CURRENT_CERT)
- Serial mismatch → 403 (DENY_SERIAL_MISMATCH)
- Valid CN + serial → success
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.agent import (
    DENY_AGENT_NOT_ACTIVE,
    DENY_MISSING_CN,
    DENY_MISSING_SERIAL,
    DENY_NO_CURRENT_CERT,
    DENY_SERIAL_MISMATCH,
    _resolve_agent,
)


def _make_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


@pytest.mark.asyncio
async def test_deny_missing_cn():
    """Missing X-Client-CN → 401."""
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc_info:
        await _resolve_agent(None, "some-serial", db)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == DENY_MISSING_CN


@pytest.mark.asyncio
async def test_deny_missing_serial():
    """Missing X-Client-Serial → 401 (fail-closed)."""
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc_info:
        await _resolve_agent("test-agent", None, db)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == DENY_MISSING_SERIAL


@pytest.mark.asyncio
async def test_deny_missing_serial_empty_string():
    """Empty string X-Client-Serial → 401 (fail-closed)."""
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc_info:
        await _resolve_agent("test-agent", "", db)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == DENY_MISSING_SERIAL


@pytest.mark.asyncio
async def test_deny_agent_not_active():
    """CN present, serial present, but no active agent → 403."""
    db = AsyncMock()
    db.execute.return_value = _make_result(None)  # No matching active agent

    with pytest.raises(HTTPException) as exc_info:
        await _resolve_agent("unknown-agent", "aa:bb:cc", db)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == DENY_AGENT_NOT_ACTIVE


@pytest.mark.asyncio
async def test_deny_no_current_cert(mock_agent):
    """Agent exists but has no valid current cert → 403."""
    db = AsyncMock()
    db.execute.side_effect = [
        _make_result(mock_agent),  # Agent found
        _make_result(None),  # No current cert
    ]

    with pytest.raises(HTTPException) as exc_info:
        await _resolve_agent(mock_agent.name, "aa:bb:cc", db)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == DENY_NO_CURRENT_CERT


@pytest.mark.asyncio
async def test_deny_serial_mismatch(mock_agent, mock_cert):
    """Agent + cert exist, but presented serial doesn't match → 403."""
    db = AsyncMock()
    db.execute.side_effect = [
        _make_result(mock_agent),
        _make_result(mock_cert),  # cert with serial_hex="abcdef1234567890"
    ]

    with pytest.raises(HTTPException) as exc_info:
        await _resolve_agent(mock_agent.name, "FF:FF:FF", db)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == DENY_SERIAL_MISMATCH


@pytest.mark.asyncio
async def test_accept_valid_serial(mock_agent, mock_cert):
    """Valid CN + matching serial → returns agent."""
    db = AsyncMock()
    db.execute.side_effect = [
        _make_result(mock_agent),
        _make_result(mock_cert),
    ]

    # mock_cert.serial_hex = "abcdef1234567890"
    # Present the same serial, colon-separated uppercase (as nginx sends it)
    serial_header = "AB:CD:EF:12:34:56:78:90"

    agent = await _resolve_agent(mock_agent.name, serial_header, db)
    assert agent is mock_agent


@pytest.mark.asyncio
async def test_accept_serial_without_colons(mock_agent, mock_cert):
    """Serial sent without colons (lowercase) → also accepted."""
    db = AsyncMock()
    db.execute.side_effect = [
        _make_result(mock_agent),
        _make_result(mock_cert),
    ]

    agent = await _resolve_agent(mock_agent.name, "abcdef1234567890", db)
    assert agent is mock_agent
