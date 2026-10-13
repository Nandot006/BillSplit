"""create person_taxonomy_scores table

Revision ID: 870a9b0bc1d9
Revises: 616f82242acf
Create Date: 2026-09-07 17:11:04.977207

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "870a9b0bc1d9"
down_revision: str | Sequence[str] | None = "616f82242acf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The 20-value combined taxonomy space (design.md SS3) and the two-value
# source enum, spelled out here (rather than imported from app.models) so
# this migration keeps working even if the Python enum's members change
# later - a migration should describe the DB state at the time it ran, not
# the current code.
_TAXONOMY_VALUES = (
    "appetizer",
    "entree",
    "side",
    "dessert",
    "drink-non-alcoholic",
    "drink-alcoholic",
    "shared-platter",
    "spicy",
    "sweet",
    "savory",
    "sour",
    "mild",
    "vegetarian",
    "vegan",
    "gluten-free",
    "dairy-free",
    "nut-free",
    "no-pork",
    "no-beef",
    "no-alcohol",
)
_TAXONOMY_SOURCE_VALUES = ("questionnaire", "learned_correction")


def upgrade() -> None:
    taxonomy_value_enum = sa.Enum(*_TAXONOMY_VALUES, name="taxonomy_value")
    taxonomy_source_enum = sa.Enum(*_TAXONOMY_SOURCE_VALUES, name="taxonomy_source")

    op.create_table(
        "person_taxonomy_scores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("taxonomy_value", taxonomy_value_enum, nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("is_hard_restriction", sa.Boolean(), nullable=False),
        sa.Column("source", taxonomy_source_enum, nullable=False),
        sa.Column("correction_count", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["people.id"],
            name=op.f("fk_person_taxonomy_scores_person_id_people"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_person_taxonomy_scores")),
        sa.UniqueConstraint(
            "person_id", "taxonomy_value", name=op.f("uq_person_taxonomy_scores_person_id")
        ),
    )


def downgrade() -> None:
    op.drop_table("person_taxonomy_scores")
    sa.Enum(name="taxonomy_value").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="taxonomy_source").drop(op.get_bind(), checkfirst=True)
