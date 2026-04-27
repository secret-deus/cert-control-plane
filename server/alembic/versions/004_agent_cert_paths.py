"""add agent.cert_paths column

Revision ID: 004_agent_cert_paths
Revises: 003_schema_reconcile_external_distribution
Create Date: 2026-04-20

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("cert_paths", JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "cert_paths")
