"""add agent_token_hash column

Revision ID: 008
Revises: 007
Create Date: 2026-05-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("agent_token_hash", sa.String(64), nullable=True))
    op.create_index("ix_agents_token_hash", "agents", ["agent_token_hash"], unique=True)
    op.drop_constraint("agents_agent_token_key", "agents", type_="unique")
    op.drop_column("agents", "agent_token")


def downgrade() -> None:
    op.add_column("agents", sa.Column("agent_token", sa.String(128), nullable=True))
    op.create_unique_constraint("agents_agent_token_key", "agents", ["agent_token"])
    op.drop_index("ix_agents_token_hash", table_name="agents")
    op.drop_column("agents", "agent_token_hash")
