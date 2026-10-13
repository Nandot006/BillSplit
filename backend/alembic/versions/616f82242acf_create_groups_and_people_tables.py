"""create groups and people tables

Revision ID: 616f82242acf
Revises: 8137720f1baa
Create Date: 2026-09-06 19:12:59.569976

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "616f82242acf"
down_revision: str | Sequence[str] | None = "8137720f1baa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("creator_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["creator_user_id"], ["users.id"], name=op.f("fk_groups_creator_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_groups")),
    )
    op.create_table(
        "people",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("supabase_user_id", sa.Uuid(), nullable=True),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("free_text_preferences", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["group_id"], ["groups.id"], name=op.f("fk_people_group_id_groups"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["supabase_user_id"], ["users.id"], name=op.f("fk_people_supabase_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_people")),
    )


def downgrade() -> None:
    op.drop_table("people")
    op.drop_table("groups")
