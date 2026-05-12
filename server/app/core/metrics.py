"""Lightweight Prometheus metrics collector.

Generates Prometheus text exposition format without depending on prometheus_client.
"""

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# In-memory counters
# ---------------------------------------------------------------------------

_request_counts: dict[str, int] = defaultdict(int)  # {method:path:status: count}
_request_durations: dict[str, list[float]] = defaultdict(list)  # {method:path: [durations]}
_distribution_counts: dict[str, int] = defaultdict(int)  # {result: count}

# UUID pattern for path normalization
_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
# Generic numeric/hex ID segments
_ID_RE = re.compile(r"/[0-9a-fA-F]{8,}")


def normalize_path(path: str) -> str:
    """Normalize URL path by replacing UUIDs and long IDs with :id."""
    path = _UUID_RE.sub(":id", path)
    path = _ID_RE.sub("/:id", path)
    return path


def record_request(method: str, path: str, status_code: int, duration: float):
    """Record an API request metric."""
    key = f"{method}:{path}:{status_code}"
    _request_counts[key] += 1
    duration_key = f"{method}:{path}"
    _request_durations[duration_key].append(duration)


def record_distribution(result: str):
    """Record a cert distribution event (success/failure)."""
    _distribution_counts[result] += 1


# ---------------------------------------------------------------------------
# DB metrics collection
# ---------------------------------------------------------------------------

async def collect_db_metrics(session: AsyncSession) -> str:
    """Query DB for business metrics, return Prometheus text format."""
    from app.models import Agent, AgentStatus, ExternalCertificate

    lines: list[str] = []
    now = datetime.now(timezone.utc)

    # --- Agent counts by status ---
    lines.append("# HELP certcp_agents_total Number of agents by status.")
    lines.append("# TYPE certcp_agents_total gauge")

    for status in AgentStatus:
        result = await session.execute(
            select(func.count()).select_from(Agent).where(Agent.status == status)
        )
        count = result.scalar() or 0
        lines.append(f'certcp_agents_total{{status="{status.value}"}} {count}')

    # --- Online agents (last_seen within 5 minutes) ---
    lines.append("# HELP certcp_agents_online Agents seen within the last 5 minutes.")
    lines.append("# TYPE certcp_agents_online gauge")
    threshold = now - timedelta(minutes=5)
    result = await session.execute(
        select(func.count()).select_from(Agent).where(
            Agent.last_seen >= threshold,
            Agent.status == AgentStatus.ACTIVE,
        )
    )
    online_count = result.scalar() or 0
    lines.append(f"certcp_agents_online {online_count}")

    # --- Certificates by expiry status ---
    lines.append("# HELP certcp_certs_total Certificates by expiry status.")
    lines.append("# TYPE certcp_certs_total gauge")

    expiring_threshold = now + timedelta(days=30)

    # Active (not expired, not expiring soon)
    result = await session.execute(
        select(func.count()).select_from(ExternalCertificate).where(
            ExternalCertificate.is_active == True,  # noqa: E712
            ExternalCertificate.not_after > expiring_threshold,
        )
    )
    active_count = result.scalar() or 0
    lines.append(f'certcp_certs_total{{status="active"}} {active_count}')

    # Expiring soon (within 30 days but not expired)
    result = await session.execute(
        select(func.count()).select_from(ExternalCertificate).where(
            ExternalCertificate.is_active == True,  # noqa: E712
            ExternalCertificate.not_after <= expiring_threshold,
            ExternalCertificate.not_after > now,
        )
    )
    expiring_count = result.scalar() or 0
    lines.append(f'certcp_certs_total{{status="expiring_soon"}} {expiring_count}')

    # Expired
    result = await session.execute(
        select(func.count()).select_from(ExternalCertificate).where(
            ExternalCertificate.is_active == True,  # noqa: E712
            ExternalCertificate.not_after <= now,
        )
    )
    expired_count = result.scalar() or 0
    lines.append(f'certcp_certs_total{{status="expired"}} {expired_count}')

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Request metrics collection
# ---------------------------------------------------------------------------

_HISTOGRAM_BUCKETS = [0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]


def format_histogram(name: str, help_text: str, labels: str, buckets: list[float], values: list[float]) -> str:
    """Format a list of values into Prometheus histogram format."""
    lines: list[str] = []
    sorted_values = sorted(values)
    total = len(sorted_values)
    cumulative = 0
    bucket_idx = 0

    for le in buckets:
        while bucket_idx < total and sorted_values[bucket_idx] <= le:
            cumulative += 1
            bucket_idx += 1
        lines.append(f'{name}_bucket{{{labels},le="{le}"}} {cumulative}')
    # +Inf bucket
    lines.append(f'{name}_bucket{{{labels},le="+Inf"}} {total}')
    lines.append(f"{name}_sum{{{labels}}} {sum(values):.6f}")
    lines.append(f"{name}_count{{{labels}}} {total}")
    return "\n".join(lines)


def collect_request_metrics() -> str:
    """Return request counter and duration metrics in Prometheus format."""
    lines: list[str] = []

    # --- Request counts ---
    if _request_counts:
        lines.append("# HELP certcp_api_requests_total Total API requests by method, path, status.")
        lines.append("# TYPE certcp_api_requests_total counter")
        for key, count in sorted(_request_counts.items()):
            method, path, status = key.rsplit(":", 2)
            lines.append(
                f'certcp_api_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}'
            )

    # --- Request duration histograms ---
    if _request_durations:
        lines.append("# HELP certcp_api_request_duration_seconds API request duration histogram.")
        lines.append("# TYPE certcp_api_request_duration_seconds histogram")
        for key, values in sorted(_request_durations.items()):
            method, path = key.split(":", 1)
            labels = f'method="{method}",path="{path}"'
            hist = format_histogram(
                "certcp_api_request_duration_seconds", "", labels,
                _HISTOGRAM_BUCKETS, values,
            )
            lines.append(hist)

    return "\n".join(lines)


def collect_distribution_metrics() -> str:
    """Return distribution counter metrics in Prometheus format."""
    lines: list[str] = []
    if _distribution_counts:
        lines.append("# HELP certcp_cert_distribution_total Certificate distribution events.")
        lines.append("# TYPE certcp_cert_distribution_total counter")
        for result, count in sorted(_distribution_counts.items()):
            lines.append(f'certcp_cert_distribution_total{{result="{result}"}} {count}')
    return "\n".join(lines)
