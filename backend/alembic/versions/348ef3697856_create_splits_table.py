"""create splits table

Revision ID: 348ef3697856
Revises: 1e54cd4d8c37
Create Date: 2026-09-10 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "348ef3697856"
down_revision: str | Sequence[str] | None = "1e54cd4d8c37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "splits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("bill_id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("item_subtotal_share", sa.Numeric(10, 2), nullable=False),
        sa.Column("tax_share", sa.Numeric(10, 2), nullable=False),
        sa.Column("tip_share", sa.Numeric(10, 2), nullable=False),
        sa.Column("total_owed", sa.Numeric(10, 2), nullable=False),
        sa.Column("is_paid", sa.Boolean(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["bill_id"],
            ["bills.id"],
            name=op.f("fk_splits_bill_id_bills"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["people.id"],
            name=op.f("fk_splits_person_id_people"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_splits")),
        sa.UniqueConstraint("bill_id", "person_id", name=op.f("uq_splits_bill_id")),
    )


def downgrade() -> None:
    op.drop_table("splits")
