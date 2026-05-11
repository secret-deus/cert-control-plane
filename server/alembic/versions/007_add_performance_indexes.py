"""add performance indexes

Revision ID: 007
Revises: 006
Create Date: 2026-05-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Dashboard Agent 在线统计
    op.create_index(
        "ix_agents_status_last_seen",
        "agents",
        ["status", "last_seen"],
    )
    # Agent 证书拉取查询
    op.create_index(
        "ix_agent_cert_assignments_agent_external",
        "agent_cert_assignments",
        ["agent_id", "external_cert_id"],
    )
    # 证书到期过滤
    op.create_index(
        "ix_external_certificates_active_expiry",
        "external_certificates",
        ["is_active", "not_after"],
    )
    # Agent 当前证书查询
    op.create_index(
        "ix_certificates_agent_current",
        "certificates",
        ["agent_id", "is_current"],
    )
    # 审计日志分页查询
    op.create_index(
        "ix_audit_logs_action_created",
        "audit_logs",
        ["action", "created_at"],
    )
    # Rollout 批次推进
    op.create_index(
        "ix_rollout_items_rollout_batch_status",
        "rollout_items",
        ["rollout_id", "batch_number", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_rollout_items_rollout_batch_status", table_name="rollout_items")
    op.drop_index("ix_audit_logs_action_created", table_name="audit_logs")
    op.drop_index("ix_certificates_agent_current", table_name="certificates")
    op.drop_index("ix_external_certificates_active_expiry", table_name="external_certificates")
    op.drop_index("ix_agent_cert_assignments_agent_external", table_name="agent_cert_assignments")
    op.drop_index("ix_agents_status_last_seen", table_name="agents")
