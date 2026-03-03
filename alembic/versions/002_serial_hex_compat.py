"""Add serial_hex for legacy databases that applied old 001 with BIGINT serial.

Revision ID: 002
Revises: 001
Create Date: 2026-03-03 00:00:00.000000

For fresh deployments (001 already creates serial_hex), this migration is a safe
no-op.  For legacy deployments that ran the original 001 with ``serial BIGINT``,
this revision:
  1. Adds ``serial_hex VARCHAR(40)`` nullable.
  2. Backfills from ``serial`` using PostgreSQL ``to_hex()``.
  3. Adds a unique constraint on ``serial_hex``.
  4. Makes ``serial_hex`` NOT NULL.
  5. Keeps the old ``serial`` column intact for safe rollback.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: str = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    """Check whether *column* exists in *table* via information_schema."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :tbl AND column_name = :col"
        ),
        {"tbl": table, "col": column},
    )
    return result.scalar() is not None


def upgrade() -> None:
    has_serial_hex = _column_exists("certificates", "serial_hex")
    has_serial = _column_exists("certificates", "serial")

    if has_serial_hex:
        # Fresh DB or already migrated — nothing to do.
        return

    if not has_serial:
        # Neither column exists — unexpected state; bail out clearly.
        raise RuntimeError(
            "certificates table has neither 'serial' nor 'serial_hex'. "
            "Cannot determine migration path."
        )

    # --- Legacy path: serial BIGINT -> serial_hex VARCHAR(40) ---

    # 1. Add nullable serial_hex column.
    op.add_column(
        "certificates",
        sa.Column("serial_hex", sa.String(40), nullable=True),
    )

    # 2. Backfill from existing serial (BIGINT -> lowercase hex string).
    op.execute(
        sa.text("UPDATE certificates SET serial_hex = lower(to_hex(serial))")
    )

    # 3. Make serial_hex NOT NULL.
    op.alter_column("certificates", "serial_hex", nullable=False)

    # 4. Add unique constraint.
    op.create_unique_constraint(
        "uq_certificates_serial_hex", "certificates", ["serial_hex"]
    )

    # Note: the old ``serial`` column is intentionally kept for rollback safety.
    # It can be dropped in a future cleanup migration after verification.


def downgrade() -> None:
    has_serial_hex = _column_exists("certificates", "serial_hex")
    has_serial = _column_exists("certificates", "serial")

    if has_serial and has_serial_hex:
        # Legacy path was applied — reverse it.
        op.drop_constraint("uq_certificates_serial_hex", "certificates", type_="unique")
        op.drop_column("certificates", "serial_hex")
    # If serial_hex was already in 001 (fresh DB), nothing to undo here.
