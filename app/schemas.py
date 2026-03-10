"""Pydantic v2 schemas for request/response."""

import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from app.models import AgentStatus, RolloutItemStatus, RolloutStatus

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated list wrapper."""
    items: list[T]
    total: int
    skip: int
    limit: int


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


class AgentRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    description: str | None
    status: AgentStatus
    fingerprint: str | None
    last_seen: datetime | None
    created_at: datetime


class AgentDetail(AgentRead):
    bootstrap_token: str | None  # Only exposed once; cleared after use


# ---------------------------------------------------------------------------
# Certificate  (no key_pem_encrypted exposed)
# ---------------------------------------------------------------------------


class CertSummary(BaseModel):
    """Lightweight cert representation for list endpoints (no PEM body)."""
    model_config = {"from_attributes": True}

    id: uuid.UUID
    agent_id: uuid.UUID
    serial_hex: str
    subject_cn: str
    not_before: datetime
    not_after: datetime
    is_current: bool
    revoked_at: datetime | None
    created_at: datetime


class CertRead(CertSummary):
    """Full cert detail including PEM (still no private key)."""
    cert_pem: str
    chain_pem: str | None


# ---------------------------------------------------------------------------
# Agent API – register & renew
# ---------------------------------------------------------------------------


class AgentRegisterRequest(BaseModel):
    bootstrap_token: str = Field(..., min_length=1)
    csr_pem: str  # PEM-encoded CSR (agent generated the private key)


class AgentRegisterResponse(BaseModel):
    cert_pem: str
    chain_pem: str | None
    agent_id: uuid.UUID


class AgentRenewRequest(BaseModel):
    csr_pem: str


class AgentRenewResponse(BaseModel):
    cert_pem: str
    chain_pem: str | None
    serial_hex: str


class HeartbeatRequest(BaseModel):
    status: str = "ok"


class HeartbeatResponse(BaseModel):
    acknowledged: bool
    pending_action: str | None  # "renew" | None


# ---------------------------------------------------------------------------
# Rollout
# ---------------------------------------------------------------------------


class RolloutCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    batch_size: int = Field(default=10, ge=1, le=1000)
    target_filter: dict | None = None  # e.g. {"name_prefix": "prod-"}


class RolloutRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    description: str | None
    status: RolloutStatus
    batch_size: int
    current_batch: int
    total_batches: int
    target_filter: dict | None
    created_by: str
    created_at: datetime
    updated_at: datetime


class RolloutItemRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    agent_id: uuid.UUID
    status: RolloutItemStatus
    batch_number: int
    previous_cert_id: uuid.UUID | None
    new_cert_id: uuid.UUID | None
    attempted_at: datetime | None
    completed_at: datetime | None
    error: str | None


class RolloutDetail(RolloutRead):
    items: list[RolloutItemRead] = []


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


class AuditLogRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: str | None
    actor: str
    details: dict | None
    ip_address: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


class DashboardAgentStats(BaseModel):
    total: int
    active: int


class DashboardCertStats(BaseModel):
    total_active: int
    expiring_soon: int


class DashboardRolloutStats(BaseModel):
    running: int


class DashboardSummary(BaseModel):
    agents: DashboardAgentStats
    certificates: DashboardCertStats
    rollouts: DashboardRolloutStats


class AgentHealth(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    liveness: str
    last_seen: datetime | None
    cert_expires_at: datetime | None
    cert_revoked_at: datetime | None = None


class CertExpiry(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    subject_cn: str
    serial_hex: str
    not_after: datetime


class AuditEvent(BaseModel):
    id: uuid.UUID
    action: str
    entity_type: str
    actor: str
    created_at: datetime
    details: dict | None = None
