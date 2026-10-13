"""create bill_item_assignments and prediction_feedback tables

Revision ID: f48e3220d4fc
Revises: 83e46fe1a73a
Create Date: 2026-09-10 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f48e3220d4fc"
down_revision: str | Sequence[str] | None = "83e46fe1a73a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bill_item_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("bill_item_id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("is_predicted", sa.Boolean(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("share_fraction", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["bill_item_id"],
            ["bill_items.id"],
            name=op.f("fk_bill_item_assignments_bill_item_id_bill_items"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["people.id"],
            name=op.f("fk_bill_item_assignments_person_id_people"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bill_item_assignments")),
        sa.UniqueConstraint(
            "bill_item_id", "person_id", name=op.f("uq_bill_item_assignments_bill_item_id")
        ),
    )

    op.create_table(
        "prediction_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("bill_item_id", sa.Uuid(), nullable=False),
        sa.Column("original_predicted_person_id", sa.Uuid(), nullable=True),
        sa.Column("corrected_person_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["bill_item_id"],
            ["bill_items.id"],
            name=op.f("fk_prediction_feedback_bill_item_id_bill_items"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["original_predicted_person_id"],
            ["people.id"],
            name=op.f("fk_prediction_feedback_original_predicted_person_id_people"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["corrected_person_id"],
            ["people.id"],
            name=op.f("fk_prediction_feedback_corrected_person_id_people"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prediction_feedback")),
    )


def downgrade() -> None:
    op.drop_table("prediction_feedback")
    op.drop_table("bill_item_assignments")
