"""drop unique constraint on certificates.serial_hex

Revision ID: 005
Revises: 004
Create Date: 2026-04-21
"""

from alembic import op


revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("certificates_serial_hex_key", "certificates", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint(
        "certificates_serial_hex_key",
        "certificates",
        ["serial_hex"],
    )
