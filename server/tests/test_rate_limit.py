"""Rate limiter guardrail tests."""

import pytest
from fastapi import HTTPException

from app.core.rate_limit import check_rate_limit, reset_rate_limits


def test_rate_limit_allows_requests_inside_window():
    reset_rate_limits()

    check_rate_limit("agent-register:127.0.0.1", limit=2, now_fn=lambda: 100.0)
    check_rate_limit("agent-register:127.0.0.1", limit=2, now_fn=lambda: 101.0)


def test_rate_limit_rejects_requests_over_limit():
    reset_rate_limits()

    check_rate_limit("agent-register:127.0.0.1", limit=1, now_fn=lambda: 100.0)
    with pytest.raises(HTTPException) as exc_info:
        check_rate_limit("agent-register:127.0.0.1", limit=1, now_fn=lambda: 101.0)

    assert exc_info.value.status_code == 429


def test_rate_limit_expires_old_entries():
    reset_rate_limits()

    check_rate_limit("agent-register:127.0.0.1", limit=1, window_seconds=60, now_fn=lambda: 100.0)
    check_rate_limit("agent-register:127.0.0.1", limit=1, window_seconds=60, now_fn=lambda: 161.0)
