"""SQLAlchemy ORM models."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AgentStatus(str, enum.Enum):
    PENDING = "pending"       # Pre-registered, awaiting bootstrap
    ACTIVE = "active"         # Active – holds a valid cert
    REVOKED = "revoked"       # Cert revoked
    EXPIRED = "expired"       # Cert expired


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
    # One-time bootstrap token; cleared after registration
    bootstrap_token: Mapped[str | None] = mapped_column(String(128), unique=True)
    bootstrap_token_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    status: Mapped[AgentStatus] = mapped_column(
        Enum(AgentStatus), default=AgentStatus.PENDING, nullable=False
    )
    # SHA-256 fingerprint of the currently active cert
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    certificates: Mapped[list["Certificate"]] = relationship(
        "Certificate", back_populates="agent", cascade="all, delete-orphan"
    )
    rollout_items: Mapped[list["RolloutItem"]] = relationship(
        "RolloutItem", back_populates="agent"
    )


class Certificate(Base):
    __tablename__ = "certificates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    serial_hex: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    subject_cn: Mapped[str] = mapped_column(String(255), nullable=False)
    not_before: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    not_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    cert_pem: Mapped[str] = mapped_column(Text, nullable=False)
    # key_pem stored Fernet-encrypted; NULL if agent generated own key (CSR flow)
    key_pem_encrypted: Mapped[str | None] = mapped_column(Text)
    chain_pem: Mapped[str | None] = mapped_column(Text)

    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    agent: Mapped["Agent"] = relationship("Agent", back_populates="certificates")


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
