"""policies accepted at optional

Revision ID: 8d2e3f4a5b6c
Revises: 7c1d2e3f4a5b
Create Date: 2026-10-17 18:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8d2e3f4a5b6c"
down_revision: str | Sequence[str] | None = "7c1d2e3f4a5b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("appointments", "policies_accepted_at", existing_type=mysql.DATETIME(), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    in_use = (
        op.get_bind().execute(sa.text("SELECT COUNT(*) FROM appointments WHERE policies_accepted_at IS NULL")).scalar()
    )
    if in_use:
        raise RuntimeError(
            f"{in_use} appointment(s) booked by the studio have no policies_accepted_at. Fill them before downgrading."
        )

    op.alter_column("appointments", "policies_accepted_at", existing_type=mysql.DATETIME(), nullable=False)
