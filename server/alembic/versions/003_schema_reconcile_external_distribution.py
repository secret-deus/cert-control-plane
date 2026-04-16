"""Reconcile legacy schema with the current external distribution model.

Revision ID: 003
Revises: 002
Create Date: 2026-03-31 00:00:00.000000

This migration fixes drift between the original bootstrap/CSR-oriented schema
and the current external certificate distribution model.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: str = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = :tbl"
        ),
        {"tbl": table},
    )
    return result.scalar() is not None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = :tbl AND column_name = :col"
        ),
        {"tbl": table, "col": column},
    )
    return result.scalar() is not None


def _constraint_exists(table: str, constraint: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_schema = current_schema() "
            "AND table_name = :tbl AND constraint_name = :cst"
        ),
        {"tbl": table, "cst": constraint},
    )
    return result.scalar() is not None


def _enum_value_exists(enum_name: str, value: str) -> bool:
    """Check if an enum value exists."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_enum "
            "JOIN pg_type ON pg_type.oid = pg_enum.enumtypid "
            "WHERE pg_type.typname = :enum_name AND pg_enum.enumlabel = :value"
        ),
        {"enum_name": enum_name, "value": value},
    )
    return result.scalar() is not None


def upgrade() -> None:
    conn = op.get_bind()

    # Align agent status labels with the current model.
    # Only rename if the old value exists (for upgrading from legacy schema)
    if _enum_value_exists("agentstatus", "PENDING"):
        conn.execute(
            sa.text(
                "ALTER TYPE agentstatus RENAME VALUE 'PENDING' TO 'PENDING_APPROVAL'"
            )
        )
    # Ensure default is set correctly
    conn.execute(
        sa.text(
            "ALTER TABLE agents ALTER COLUMN status SET DEFAULT 'PENDING_APPROVAL'"
        )
    )

    if not _column_exists("agents", "agent_token"):
        op.add_column("agents", sa.Column("agent_token", sa.String(128), nullable=True))
    if not _constraint_exists("agents", "agents_agent_token_key"):
        op.create_unique_constraint("agents_agent_token_key", "agents", ["agent_token"])

    if not _column_exists("certificates", "external_cert_id"):
        op.add_column(
            "certificates",
            sa.Column("external_cert_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
    if not _column_exists("certificates", "local_path"):
        op.add_column(
            "certificates",
            sa.Column("local_path", sa.String(1024), nullable=True),
        )

    if not _table_exists("external_certificates"):
        op.create_table(
            "external_certificates",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text),
            sa.Column("cert_pem", sa.Text, nullable=False),
            sa.Column("key_pem_encrypted", sa.Text, nullable=False),
            sa.Column("chain_pem", sa.Text),
            sa.Column("subject_cn", sa.String(255), nullable=False),
            sa.Column("serial_hex", sa.String(40), nullable=False),
            sa.Column("not_before", sa.DateTime(timezone=True), nullable=False),
            sa.Column("not_after", sa.DateTime(timezone=True), nullable=False),
            sa.Column("provider", sa.String(100)),
            sa.Column("external_id", sa.String(255)),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("auto_renew", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint("serial_hex", name="uq_external_certificates_serial_hex"),
        )

    if not _table_exists("agent_cert_assignments"):
        op.create_table(
            "agent_cert_assignments",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "agent_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("agents.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "external_cert_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("external_certificates.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("local_path", sa.String(1024), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    if not _constraint_exists("certificates", "certificates_external_cert_id_fkey"):
        op.create_foreign_key(
            "certificates_external_cert_id_fkey",
            "certificates",
            "external_certificates",
            ["external_cert_id"],
            ["id"],
        )


def downgrade() -> None:
    conn = op.get_bind()

    if _constraint_exists("certificates", "certificates_external_cert_id_fkey"):
        op.drop_constraint("certificates_external_cert_id_fkey", "certificates", type_="foreignkey")

    if _table_exists("agent_cert_assignments"):
        op.drop_table("agent_cert_assignments")

    if _table_exists("external_certificates"):
        op.drop_table("external_certificates")

    if _column_exists("certificates", "local_path"):
        op.drop_column("certificates", "local_path")
    if _column_exists("certificates", "external_cert_id"):
        op.drop_column("certificates", "external_cert_id")

    if _constraint_exists("agents", "agents_agent_token_key"):
        op.drop_constraint("agents_agent_token_key", "agents", type_="unique")
    if _column_exists("agents", "agent_token"):
        op.drop_column("agents", "agent_token")

    conn.execute(
        sa.text("ALTER TABLE agents ALTER COLUMN status SET DEFAULT 'PENDING'")
    )
    conn.execute(
        sa.text(
            "ALTER TYPE agentstatus RENAME VALUE 'PENDING_APPROVAL' TO 'PENDING'"
        )
    )
