"""add other service

Revision ID: 7c1d2e3f4a5b
Revises: 64a10f560aa6
Create Date: 2026-10-17 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c1d2e3f4a5b"
down_revision: str | Sequence[str] | None = "64a10f560aa6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENT_SERVICES = ("APPLICATION", "MAINTENANCE", "REMOVAL")
# Both columns use the same Service enum, so both must accept the new value.
TABLES = ("appointments", "service_prices")


def upgrade() -> None:
    """Upgrade schema."""
    for table in TABLES:
        op.alter_column(
            table,
            "service",
            existing_type=mysql.ENUM(*CURRENT_SERVICES),
            type_=sa.Enum(*CURRENT_SERVICES, "OTHER", name="service"),
            existing_nullable=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    for table in TABLES:
        in_use = op.get_bind().execute(sa.text(f"SELECT COUNT(*) FROM {table} WHERE service = 'OTHER'")).scalar()
        if in_use:
            raise RuntimeError(
                f"{in_use} row(s) in {table} use the OTHER service. Change them before downgrading, so no data is lost."
            )

    for table in TABLES:
        op.alter_column(
            table,
            "service",
            existing_type=mysql.ENUM(*CURRENT_SERVICES, "OTHER"),
            type_=sa.Enum(*CURRENT_SERVICES, name="service"),
            existing_nullable=False,
        )
