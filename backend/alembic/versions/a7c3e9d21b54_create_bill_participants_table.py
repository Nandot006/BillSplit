"""create bill_participants table

Per-bill participants (decision 2026-11-20): which of a group's people were
actually on a bill. Existing bills are backfilled with every person in their
group, which is exactly how splits/predictions behaved before this table
existed - so no existing bill's numbers change.

Revision ID: a7c3e9d21b54
Revises: 348ef3697856
Create Date: 2026-11-20 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c3e9d21b54"
down_revision: str | Sequence[str] | None = "348ef3697856"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bill_participants",
        sa.Column("bill_id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["bill_id"],
            ["bills.id"],
            name=op.f("fk_bill_participants_bill_id_bills"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["people.id"],
            name=op.f("fk_bill_participants_person_id_people"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("bill_id", "person_id", name=op.f("pk_bill_participants")),
    )
    op.execute(
        """
        INSERT INTO bill_participants (bill_id, person_id)
        SELECT bills.id, people.id
        FROM bills JOIN people ON people.group_id = bills.group_id
        """
    )


def downgrade() -> None:
    op.drop_table("bill_participants")
