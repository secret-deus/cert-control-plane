"""Initial schema

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")

    op.create_table(
        "agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("bootstrap_token", sa.String(128), unique=True),
        sa.Column("bootstrap_token_created_at", sa.DateTime(timezone=True)),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "active", "revoked", "expired",
                name="agentstatus",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("fingerprint", sa.String(64)),
        sa.Column("last_seen", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "certificates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("serial_hex", sa.String(40), unique=True, nullable=False),
        sa.Column("subject_cn", sa.String(255), nullable=False),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=False),
        sa.Column("not_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cert_pem", sa.Text, nullable=False),
        sa.Column("key_pem_encrypted", sa.Text),
        sa.Column("chain_pem", sa.Text),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_certs_agent_id", "certificates", ["agent_id"])
    op.create_index("ix_certs_is_current", "certificates", ["is_current"])

    op.create_table(
        "rollouts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "running", "paused", "completed", "failed", "rolled_back",
                name="rolloutstatus",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("batch_size", sa.Integer, nullable=False, server_default="10"),
        sa.Column("current_batch", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_batches", sa.Integer, nullable=False, server_default="0"),
        sa.Column("target_filter", postgresql.JSON),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "rollout_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "rollout_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rollouts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "in_progress", "completed", "failed", "rolled_back",
                name="rolloutitemstatus",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("batch_number", sa.Integer, nullable=False),
        sa.Column("previous_cert_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("certificates.id")),
        sa.Column("new_cert_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("certificates.id")),
        sa.Column("attempted_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.Text),
    )
    op.create_index("ix_items_rollout_id", "rollout_items", ["rollout_id"])
    op.create_index("ix_items_agent_id", "rollout_items", ["agent_id"])
    op.create_index("ix_items_status", "rollout_items", ["status"])

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", sa.String(255)),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("details", postgresql.JSON),
        sa.Column("ip_address", sa.String(45)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_audit_entity", "audit_logs", ["entity_type", "entity_id"])
    op.create_index("ix_audit_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("rollout_items")
    op.drop_table("rollouts")
    op.drop_table("certificates")
    op.drop_table("agents")
    op.execute("DROP TYPE IF EXISTS rolloutitemstatus")
    op.execute("DROP TYPE IF EXISTS rolloutstatus")
    op.execute("DROP TYPE IF EXISTS agentstatus")
