"""Pydantic v2 schemas for request/response."""

import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from app.models import (
    AgentStatus,
    KubernetesClusterConnectionStatus,
    KubernetesSecretDryRunAction,
    KubernetesSecretDryRunStatus,
    KubernetesSecretHealthStatus,
    KubernetesSecretLifecycleStatus,
    KubernetesSecretOperationAction,
    KubernetesSecretOperationStatus,
    RolloutItemStatus,
    RolloutStatus,
)

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
    cert_paths: list[str] | None = None
    # Enhanced fields for UI
    liveness: str | None = None  # 'online' | 'delayed' | 'offline'
    cert_count: int = 0
    expiring_soon_count: int = 0


class AgentCertDetail(BaseModel):
    """Certificate detail for an agent."""

    local_path: str
    cert_name: str
    subject_cn: str
    not_after: datetime
    days_remaining: int
    urgency: str  # 'expired' | 'critical' | 'warning' | 'normal'


class AgentDetailRead(AgentRead):
    """Agent detail with certificate information."""

    certs: list[AgentCertDetail] = []


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
    key_pem: str | None = None  # Decrypted plain-text private key
    chain_pem: str | None = None
    not_after: datetime | None = None


class AgentFetchCertsRequest(BaseModel):
    """Batch cert check: agent sends its local cert table."""

    certs: list[CertCheckItem]


class AgentFetchCertsResponse(BaseModel):
    """Batch cert update response."""

    updates: list[CertUpdateItem]


class ReportCertItem(BaseModel):
    """One deployed cert entry reported by agent."""

    local_path: str
    cert_pem: str
    chain_pem: str | None = None


class AgentReportCertsRequest(BaseModel):
    """Agent reports deployed certs after successful deployment."""

    certs: list[ReportCertItem]


class AgentReportCertsResponse(BaseModel):
    """Response to report-certs."""

    recorded: int


# ---------------------------------------------------------------------------
# External Certificate (uploaded from providers like 阿里云, Let's Encrypt)
# ---------------------------------------------------------------------------


class ExternalCertCreate(BaseModel):
    """Upload external certificate"""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    cert_pem: str  # Certificate PEM
    key_pem: str  # Private key PEM (will be encrypted)
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


class FilesDetected(BaseModel):
    """Files detected in archive"""

    cert: str
    key: str
    chain: str | None = None


class ExternalCertArchiveUploadResponse(BaseModel):
    """Response after uploading certificate archive"""

    id: uuid.UUID
    name: str
    subject_cn: str
    serial_hex: str
    not_after: datetime
    files_detected: FilesDetected
    san_domains: list[str]
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


class BatchAssignRequest(BaseModel):
    external_cert_id: uuid.UUID
    agent_ids: list[uuid.UUID]
    local_path: str = Field(..., min_length=1, max_length=1024)


class BatchAssignResult(BaseModel):
    success: int
    failed: int
    assignments: list[AgentCertAssignmentRead]


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
# Kubernetes Secret distribution
# ---------------------------------------------------------------------------


class KubernetesClusterCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    environment: str | None = Field(default=None, max_length=100)
    kubeconfig: str = Field(..., min_length=1)
    default_namespace: str | None = Field(default=None, max_length=255)


class KubernetesClusterRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    environment: str | None
    api_server: str
    default_namespace: str | None
    connection_status: KubernetesClusterConnectionStatus
    last_checked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class KubernetesClusterTestConnectionResponse(BaseModel):
    cluster_id: uuid.UUID
    status: KubernetesClusterConnectionStatus
    version: str | None = None
    default_namespace: str | None = None
    message: str


class KubernetesClusterCredentialsUpdate(BaseModel):
    kubeconfig: str = Field(..., min_length=1)
    default_namespace: str | None = Field(default=None, max_length=255)


class KubernetesSecretAssignmentCreate(BaseModel):
    cluster_id: uuid.UUID
    namespace: str = Field(..., min_length=1, max_length=255)
    secret_name: str = Field(..., min_length=1, max_length=255)
    external_cert_id: uuid.UUID
    auto_track_latest: bool = True
    auto_deploy: bool = False


class KubernetesSecretAssignmentRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    cluster_id: uuid.UUID
    external_cert_id: uuid.UUID
    namespace: str
    secret_name: str
    lifecycle_status: KubernetesSecretLifecycleStatus
    health_status: KubernetesSecretHealthStatus
    auto_track_latest: bool
    auto_deploy: bool
    pending_update: bool
    current_resource_version: str | None
    current_serial_hex: str | None
    last_snapshot_serial_hex: str | None
    last_deployed_at: datetime | None
    last_validated_at: datetime | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    cluster_name: str | None = None
    external_cert_subject_cn: str | None = None


class KubernetesDryRunRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    cluster_id: uuid.UUID
    assignment_id: uuid.UUID
    action: KubernetesSecretDryRunAction
    external_cert_id: uuid.UUID | None
    namespace: str
    secret_name: str
    current_resource_version: str | None
    diff: list[dict] | None
    status: KubernetesSecretDryRunStatus
    expires_at: datetime
    created_by: str
    created_at: datetime


class KubernetesDryRunConfirmRequest(BaseModel):
    dry_run_id: uuid.UUID


class KubernetesSecretOperationRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    cluster_id: uuid.UUID
    assignment_id: uuid.UUID | None
    action: KubernetesSecretOperationAction
    status: KubernetesSecretOperationStatus
    dry_run_id: uuid.UUID | None
    external_cert_id: uuid.UUID | None
    resource_version_before: str | None
    resource_version_after: str | None
    serial_before: str | None
    serial_after: str | None
    diff: list[dict] | None
    error_code: str | None
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None
    created_by: str


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
