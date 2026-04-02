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


# ---------------------------------------------------------------------------
# Agent API – TOFU Registration
# ---------------------------------------------------------------------------


class AgentRegisterRequest(BaseModel):
    """Agent TOFU registration request: send name + public key fingerprint."""
    name: str = Field(..., min_length=1, max_length=255)
    fingerprint: str = Field(..., description="SHA256(DER public key) as hex")


class AgentRegisterResponse(BaseModel):
    """Response to registration request."""
    status: str  # "pending" | "approved"
    agent_id: uuid.UUID
    agent_token: str | None = None  # Only set when status == "approved"
    message: str


class AgentRegisterStatusResponse(BaseModel):
    """Response to registration status poll."""
    status: str  # "pending_approval" | "approved" | "rejected"
    agent_token: str | None = None  # Only set when approved


# ---------------------------------------------------------------------------
# Agent API – Heartbeat
# ---------------------------------------------------------------------------


class HeartbeatRequest(BaseModel):
    status: str = "ok"


class HeartbeatResponse(BaseModel):
    acknowledged: bool


# ---------------------------------------------------------------------------
# Agent API – Batch cert fetch
# ---------------------------------------------------------------------------


class CertCheckItem(BaseModel):
    """One entry from agent's local cert table."""
    local_path: str
    current_not_after: datetime | None = None  # None if cert not yet deployed


class CertUpdateItem(BaseModel):
    """Server response for one cert path."""
    local_path: str
    has_update: bool
    cert_pem: str | None = None
    key_pem: str | None = None   # Decrypted plain-text private key
    chain_pem: str | None = None
    not_after: datetime | None = None


class AgentFetchCertsRequest(BaseModel):
    """Batch cert check: agent sends its local cert table."""
    certs: list[CertCheckItem]


class AgentFetchCertsResponse(BaseModel):
    """Batch cert update response."""
    updates: list[CertUpdateItem]


class DeployedCertReportItem(BaseModel):
    """One currently deployed cert on the agent host."""
    local_path: str
    cert_pem: str
    chain_pem: str | None = None


class AgentReportCertsRequest(BaseModel):
    """Current cert inventory reported by the agent."""
    certs: list[DeployedCertReportItem]


class AgentReportCertsResponse(BaseModel):
    """Result of syncing current cert inventory."""
    recorded: int


# ---------------------------------------------------------------------------
# External Certificate (uploaded from providers like 阿里云, Let's Encrypt)
# ---------------------------------------------------------------------------


class ExternalCertCreate(BaseModel):
    """Upload external certificate"""
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    cert_pem: str  # Certificate PEM
    key_pem: str   # Private key PEM (will be encrypted)
    chain_pem: str | None = None  # Certificate chain PEM
    provider: str | None = None  # e.g., "aliyun", "letsencrypt"
    external_id: str | None = None  # Provider's certificate ID


class ExternalCertSummary(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    description: str | None
    subject_cn: str
    serial_hex: str
    not_before: datetime
    not_after: datetime
    provider: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ExternalCertRead(ExternalCertSummary):
    """Full external cert detail"""
    cert_pem: str
    chain_pem: str | None


class ExternalCertUploadResponse(BaseModel):
    """Response after uploading certificate"""
    id: uuid.UUID
    name: str
    subject_cn: str
    serial_hex: str
    not_after: datetime
    message: str


# ---------------------------------------------------------------------------
# Agent Cert Assignment
# ---------------------------------------------------------------------------


class AgentCertAssignRequest(BaseModel):
    """Assign an external cert to an agent for a specific local path."""
    external_cert_id: uuid.UUID
    local_path: str = Field(..., min_length=1, max_length=1024)


class AgentCertAssignmentRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    agent_id: uuid.UUID
    external_cert_id: uuid.UUID
    local_path: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Certificate  (no private key exposed)
# ---------------------------------------------------------------------------


class CertSummary(BaseModel):
    """Lightweight cert representation for list endpoints."""
    model_config = {"from_attributes": True}

    id: uuid.UUID
    agent_id: uuid.UUID
    external_cert_id: uuid.UUID | None
    local_path: str | None
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
    pending_approval: int


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
