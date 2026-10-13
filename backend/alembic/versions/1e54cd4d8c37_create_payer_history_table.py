"""create payer_history table

Revision ID: 1e54cd4d8c37
Revises: f48e3220d4fc
Create Date: 2026-09-10 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1e54cd4d8c37"
down_revision: str | Sequence[str] | None = "f48e3220d4fc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payer_history",
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("payment_count", sa.Integer(), nullable=False),
        sa.Column("last_paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
            name=op.f("fk_payer_history_group_id_groups"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["people.id"],
            name=op.f("fk_payer_history_person_id_people"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("group_id", "person_id", name=op.f("pk_payer_history")),
    )


def downgrade() -> None:
    op.drop_table("payer_history")
