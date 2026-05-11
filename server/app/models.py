"""SQLAlchemy ORM models."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AgentStatus(str, enum.Enum):
    PENDING_APPROVAL = "pending_approval"  # Registered fingerprint, awaiting admin approval
    ACTIVE = "active"                       # Approved, holds agent_token
    REVOKED = "revoked"                     # Revoked by admin


class RolloutStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class RolloutItemStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class KubernetesClusterConnectionStatus(str, enum.Enum):
    UNKNOWN = "unknown"
    ACTIVE = "active"
    FAILED = "failed"


class KubernetesSecretLifecycleStatus(str, enum.Enum):
    PENDING = "pending"
    ADOPTED = "adopted"
    DEPLOYED = "deployed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class KubernetesSecretHealthStatus(str, enum.Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    MISSING = "missing"
    UNMANAGED = "unmanaged"
    SERIAL_MISMATCH = "serial_mismatch"
    INVALID_SECRET = "invalid_secret"
    RBAC_ERROR = "rbac_error"
    CLUSTER_UNREACHABLE = "cluster_unreachable"


class KubernetesSecretDryRunAction(str, enum.Enum):
    ADOPT = "adopt"
    DEPLOY = "deploy"
    ROLLBACK = "rollback"


class KubernetesSecretDryRunStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"


class KubernetesSecretOperationAction(str, enum.Enum):
    TEST_CONNECTION = "test_connection"
    ADOPT = "adopt"
    DEPLOY = "deploy"
    ROLLBACK = "rollback"
    VALIDATE = "validate"


class KubernetesSecretOperationStatus(str, enum.Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[AgentStatus] = mapped_column(
        Enum(AgentStatus), default=AgentStatus.PENDING_APPROVAL, nullable=False
    )
    # SHA-256 fingerprint of agent's public key (TOFU identity)
    fingerprint: Mapped[str | None] = mapped_column(String(64), unique=True)
    # SHA-256 hash of X-Agent-Token. Plaintext token is returned once and never stored.
    agent_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Cert paths reported by agent during fetch-certs (JSON list of local_path strings)
    cert_paths: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    cert_assignments: Mapped[list["AgentCertAssignment"]] = relationship(
        "AgentCertAssignment", back_populates="agent", cascade="all, delete-orphan"
    )
    rollout_items: Mapped[list["RolloutItem"]] = relationship(
        "RolloutItem", back_populates="agent"
    )


class ExternalCertificate(Base):
    """External certificates uploaded from providers (阿里云, Let's Encrypt, etc.)"""
    __tablename__ = "external_certificates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Certificate data
    cert_pem: Mapped[str] = mapped_column(Text, nullable=False)
    key_pem_encrypted: Mapped[str] = mapped_column(Text, nullable=False)  # Fernet encrypted
    chain_pem: Mapped[str | None] = mapped_column(Text)

    # Parsed from certificate
    subject_cn: Mapped[str] = mapped_column(String(255), nullable=False)
    serial_hex: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    not_before: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    not_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Provider info
    provider: Mapped[str | None] = mapped_column(String(100))  # aliyun, letsencrypt, etc.
    external_id: Mapped[str | None] = mapped_column(String(255))  # Provider's cert ID

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AgentCertAssignment(Base):
    """Maps an agent's local file path to an external certificate on the platform."""
    __tablename__ = "agent_cert_assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    external_cert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("external_certificates.id", ondelete="CASCADE"), nullable=False
    )
    # Local path on the agent host, e.g. "/etc/nginx/ssl/api.example.com.crt"
    local_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    agent: Mapped["Agent"] = relationship("Agent", back_populates="cert_assignments")
    external_cert: Mapped["ExternalCertificate"] = relationship("ExternalCertificate")


class Certificate(Base):
    """Audit record for certificates deployed to agents (via AgentCertAssignment)."""
    __tablename__ = "certificates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    external_cert_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("external_certificates.id"), nullable=True
    )
    local_path: Mapped[str | None] = mapped_column(String(1024))

    serial_hex: Mapped[str] = mapped_column(String(40), nullable=False)
    subject_cn: Mapped[str] = mapped_column(String(255), nullable=False)
    not_before: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    not_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    cert_pem: Mapped[str] = mapped_column(Text, nullable=False)
    chain_pem: Mapped[str | None] = mapped_column(Text)

    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    agent: Mapped["Agent"] = relationship("Agent")


class KubernetesCluster(Base):
    """Target Kubernetes cluster reachable through an uploaded SA kubeconfig."""
    __tablename__ = "kubernetes_clusters"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    environment: Mapped[str | None] = mapped_column(String(100))
    api_server: Mapped[str] = mapped_column(String(1024), nullable=False)
    default_namespace: Mapped[str | None] = mapped_column(String(255))
    kubeconfig_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    connection_status: Mapped[KubernetesClusterConnectionStatus] = mapped_column(
        Enum(KubernetesClusterConnectionStatus),
        default=KubernetesClusterConnectionStatus.UNKNOWN,
        nullable=False,
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    assignments: Mapped[list["KubernetesSecretAssignment"]] = relationship(
        "KubernetesSecretAssignment",
        back_populates="cluster",
        cascade="all, delete-orphan",
    )


class KubernetesSecretAssignment(Base):
    """Explicit mapping from an external certificate to one Kubernetes Secret."""
    __tablename__ = "kubernetes_secret_assignments"
    __table_args__ = (
        Index(
            "uq_k8s_secret_assignments_active_target",
            "cluster_id",
            "namespace",
            "secret_name",
            unique=True,
            postgresql_where=text("is_active = true"),
            sqlite_where=text("is_active = 1"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cluster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kubernetes_clusters.id", ondelete="CASCADE"), nullable=False
    )
    external_cert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("external_certificates.id"), nullable=False
    )
    namespace: Mapped[str] = mapped_column(String(255), nullable=False)
    secret_name: Mapped[str] = mapped_column(String(255), nullable=False)
    lifecycle_status: Mapped[KubernetesSecretLifecycleStatus] = mapped_column(
        Enum(KubernetesSecretLifecycleStatus),
        default=KubernetesSecretLifecycleStatus.PENDING,
        nullable=False,
    )
    health_status: Mapped[KubernetesSecretHealthStatus] = mapped_column(
        Enum(KubernetesSecretHealthStatus),
        default=KubernetesSecretHealthStatus.UNKNOWN,
        nullable=False,
    )
    auto_track_latest: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_deploy: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pending_update: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_resource_version: Mapped[str | None] = mapped_column(String(255))
    current_serial_hex: Mapped[str | None] = mapped_column(String(40))
    last_snapshot_encrypted: Mapped[str | None] = mapped_column(Text)
    last_snapshot_serial_hex: Mapped[str | None] = mapped_column(String(40))
    last_deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    cluster: Mapped["KubernetesCluster"] = relationship(
        "KubernetesCluster", back_populates="assignments"
    )
    external_cert: Mapped["ExternalCertificate"] = relationship("ExternalCertificate")


class KubernetesSecretDryRun(Base):
    """Persisted dry-run token required before any Kubernetes Secret write."""
    __tablename__ = "kubernetes_secret_dry_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cluster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kubernetes_clusters.id", ondelete="CASCADE"), nullable=False
    )
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kubernetes_secret_assignments.id", ondelete="CASCADE"),
        nullable=False,
    )
    action: Mapped[KubernetesSecretDryRunAction] = mapped_column(
        Enum(KubernetesSecretDryRunAction), nullable=False
    )
    external_cert_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("external_certificates.id"), nullable=True
    )
    namespace: Mapped[str] = mapped_column(String(255), nullable=False)
    secret_name: Mapped[str] = mapped_column(String(255), nullable=False)
    current_resource_version: Mapped[str | None] = mapped_column(String(255))
    diff: Mapped[list[dict] | None] = mapped_column(JSON)
    status: Mapped[KubernetesSecretDryRunStatus] = mapped_column(
        Enum(KubernetesSecretDryRunStatus),
        default=KubernetesSecretDryRunStatus.PENDING,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class KubernetesSecretOperation(Base):
    """Audit-grade operation record for K8s Secret actions."""
    __tablename__ = "kubernetes_secret_operations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cluster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kubernetes_clusters.id", ondelete="CASCADE"), nullable=False
    )
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kubernetes_secret_assignments.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[KubernetesSecretOperationAction] = mapped_column(
        Enum(KubernetesSecretOperationAction), nullable=False
    )
    status: Mapped[KubernetesSecretOperationStatus] = mapped_column(
        Enum(KubernetesSecretOperationStatus),
        default=KubernetesSecretOperationStatus.RUNNING,
        nullable=False,
    )
    dry_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kubernetes_secret_dry_runs.id"), nullable=True
    )
    external_cert_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("external_certificates.id"), nullable=True
    )
    resource_version_before: Mapped[str | None] = mapped_column(String(255))
    resource_version_after: Mapped[str | None] = mapped_column(String(255))
    serial_before: Mapped[str | None] = mapped_column(String(40))
    serial_after: Mapped[str | None] = mapped_column(String(40))
    diff: Mapped[list[dict] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)


class Rollout(Base):
    __tablename__ = "rollouts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[RolloutStatus] = mapped_column(
        Enum(RolloutStatus), default=RolloutStatus.PENDING, nullable=False
    )
    batch_size: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    current_batch: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_batches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # JSON filter for targeting agents (e.g. {"name_prefix": "prod-"})
    target_filter: Mapped[dict | None] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    items: Mapped[list["RolloutItem"]] = relationship(
        "RolloutItem", back_populates="rollout", cascade="all, delete-orphan"
    )


class RolloutItem(Base):
    __tablename__ = "rollout_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    rollout_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rollouts.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False
    )
    status: Mapped[RolloutItemStatus] = mapped_column(
        Enum(RolloutItemStatus), default=RolloutItemStatus.PENDING, nullable=False
    )
    batch_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Saved before cert rotation so rollback can restore
    previous_cert_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("certificates.id")
    )
    new_cert_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("certificates.id")
    )
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)

    rollout: Mapped["Rollout"] = relationship("Rollout", back_populates="items")
    agent: Mapped["Agent"] = relationship("Agent", back_populates="rollout_items")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(255))
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
