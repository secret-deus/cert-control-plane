"""add kubernetes secret deployment tables

Revision ID: 006
Revises: 005
Create Date: 2026-05-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kubernetes_clusters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("environment", sa.String(100)),
        sa.Column("api_server", sa.String(1024), nullable=False),
        sa.Column("default_namespace", sa.String(255)),
        sa.Column("kubeconfig_encrypted", sa.Text, nullable=False),
        sa.Column(
            "connection_status",
            sa.Enum("UNKNOWN", "ACTIVE", "FAILED", name="kubernetesclusterconnectionstatus"),
            nullable=False,
            server_default="UNKNOWN",
        ),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_kubernetes_clusters_name", "kubernetes_clusters", ["name"])

    op.create_table(
        "kubernetes_secret_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "cluster_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kubernetes_clusters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "external_cert_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("external_certificates.id"),
            nullable=False,
        ),
        sa.Column("namespace", sa.String(255), nullable=False),
        sa.Column("secret_name", sa.String(255), nullable=False),
        sa.Column(
            "lifecycle_status",
            sa.Enum(
                "PENDING", "ADOPTED", "DEPLOYED", "FAILED", "ROLLED_BACK",
                name="kubernetessecretlifecyclestatus",
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "health_status",
            sa.Enum(
                "UNKNOWN",
                "HEALTHY",
                "MISSING",
                "UNMANAGED",
                "SERIAL_MISMATCH",
                "INVALID_SECRET",
                "RBAC_ERROR",
                "CLUSTER_UNREACHABLE",
                name="kubernetessecrethealthstatus",
            ),
            nullable=False,
            server_default="UNKNOWN",
        ),
        sa.Column("auto_track_latest", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("auto_deploy", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("pending_update", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("current_resource_version", sa.String(255)),
        sa.Column("current_serial_hex", sa.String(40)),
        sa.Column("last_snapshot_encrypted", sa.Text),
        sa.Column("last_snapshot_serial_hex", sa.String(40)),
        sa.Column("last_deployed_at", sa.DateTime(timezone=True)),
        sa.Column("last_validated_at", sa.DateTime(timezone=True)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_k8s_secret_assignments_cluster_id", "kubernetes_secret_assignments", ["cluster_id"])
    op.create_index("ix_k8s_secret_assignments_external_cert_id", "kubernetes_secret_assignments", ["external_cert_id"])
    op.create_index(
        "uq_k8s_secret_assignments_active_target",
        "kubernetes_secret_assignments",
        ["cluster_id", "namespace", "secret_name"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )

    op.create_table(
        "kubernetes_secret_dry_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "cluster_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kubernetes_clusters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "assignment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kubernetes_secret_assignments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "action",
            sa.Enum("ADOPT", "DEPLOY", "ROLLBACK", name="kubernetessecretdryrunaction"),
            nullable=False,
        ),
        sa.Column("external_cert_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("external_certificates.id")),
        sa.Column("namespace", sa.String(255), nullable=False),
        sa.Column("secret_name", sa.String(255), nullable=False),
        sa.Column("current_resource_version", sa.String(255)),
        sa.Column("diff", postgresql.JSON),
        sa.Column(
            "status",
            sa.Enum("PENDING", "CONFIRMED", "EXPIRED", name="kubernetessecretdryrunstatus"),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_k8s_secret_dry_runs_assignment_id", "kubernetes_secret_dry_runs", ["assignment_id"])
    op.create_index("ix_k8s_secret_dry_runs_status", "kubernetes_secret_dry_runs", ["status"])

    op.create_table(
        "kubernetes_secret_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "cluster_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kubernetes_clusters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "assignment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kubernetes_secret_assignments.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "action",
            sa.Enum(
                "TEST_CONNECTION", "ADOPT", "DEPLOY", "ROLLBACK", "VALIDATE",
                name="kubernetessecretoperationaction",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("RUNNING", "SUCCEEDED", "FAILED", name="kubernetessecretoperationstatus"),
            nullable=False,
            server_default="RUNNING",
        ),
        sa.Column("dry_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("kubernetes_secret_dry_runs.id")),
        sa.Column("external_cert_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("external_certificates.id")),
        sa.Column("resource_version_before", sa.String(255)),
        sa.Column("resource_version_after", sa.String(255)),
        sa.Column("serial_before", sa.String(40)),
        sa.Column("serial_after", sa.String(40)),
        sa.Column("diff", postgresql.JSON),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(255), nullable=False),
    )
    op.create_index("ix_k8s_secret_operations_cluster_id", "kubernetes_secret_operations", ["cluster_id"])
    op.create_index("ix_k8s_secret_operations_assignment_id", "kubernetes_secret_operations", ["assignment_id"])
    op.create_index("ix_k8s_secret_operations_status", "kubernetes_secret_operations", ["status"])
    op.create_index("ix_k8s_secret_operations_started_at", "kubernetes_secret_operations", ["started_at"])


def downgrade() -> None:
    op.drop_table("kubernetes_secret_operations")
    op.drop_table("kubernetes_secret_dry_runs")
    op.drop_index("uq_k8s_secret_assignments_active_target", table_name="kubernetes_secret_assignments")
    op.drop_table("kubernetes_secret_assignments")
    op.drop_table("kubernetes_clusters")
    op.execute("DROP TYPE IF EXISTS kubernetessecretoperationstatus")
    op.execute("DROP TYPE IF EXISTS kubernetessecretoperationaction")
    op.execute("DROP TYPE IF EXISTS kubernetessecretdryrunstatus")
    op.execute("DROP TYPE IF EXISTS kubernetessecretdryrunaction")
    op.execute("DROP TYPE IF EXISTS kubernetessecrethealthstatus")
    op.execute("DROP TYPE IF EXISTS kubernetessecretlifecyclestatus")
    op.execute("DROP TYPE IF EXISTS kubernetesclusterconnectionstatus")
