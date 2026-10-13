"""create bills bill_items and tag join tables

Revision ID: 83e46fe1a73a
Revises: 870a9b0bc1d9
Create Date: 2026-09-07 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "83e46fe1a73a"
down_revision: str | Sequence[str] | None = "870a9b0bc1d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BASE_TYPE_VALUES = (
    "appetizer",
    "entree",
    "side",
    "dessert",
    "drink-non-alcoholic",
    "drink-alcoholic",
    "shared-platter",
)
_FLAVOR_TAG_VALUES = ("spicy", "sweet", "savory", "sour", "mild")
_DIETARY_FLAG_VALUES = (
    "vegetarian",
    "vegan",
    "gluten-free",
    "dairy-free",
    "nut-free",
    "no-pork",
    "no-beef",
    "no-alcohol",
)
_BILL_STATUS_VALUES = (
    "uploading",
    "processing",
    "needs_manual_entry",
    "needs_review",
    "open",
    "closed",
)


def upgrade() -> None:
    base_type_enum = sa.Enum(*_BASE_TYPE_VALUES, name="base_type")
    flavor_tag_enum = sa.Enum(*_FLAVOR_TAG_VALUES, name="flavor_tag")
    dietary_flag_enum = sa.Enum(*_DIETARY_FLAG_VALUES, name="dietary_flag")
    bill_status_enum = sa.Enum(*_BILL_STATUS_VALUES, name="bill_status")

    op.create_table(
        "bills",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("image_storage_path", sa.String(), nullable=True),
        sa.Column("merchant_name", sa.String(), nullable=True),
        sa.Column("bill_date", sa.Date(), nullable=True),
        sa.Column("subtotal", sa.Numeric(10, 2), nullable=True),
        sa.Column("tax_total", sa.Numeric(10, 2), nullable=True),
        sa.Column("tip_total", sa.Numeric(10, 2), nullable=False),
        sa.Column("grand_total", sa.Numeric(10, 2), nullable=True),
        sa.Column("status", bill_status_enum, nullable=False),
        sa.Column("payer_person_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["group_id"], ["groups.id"], name=op.f("fk_bills_group_id_groups"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["payer_person_id"], ["people.id"], name=op.f("fk_bills_payer_person_id_people")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bills")),
    )

    op.create_table(
        "bill_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("bill_id", sa.Uuid(), nullable=False),
        sa.Column("raw_ocr_text", sa.Text(), nullable=True),
        sa.Column("parsed_name", sa.String(), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("base_type", base_type_enum, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["bill_id"], ["bills.id"], name=op.f("fk_bill_items_bill_id_bills"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bill_items")),
    )

    op.create_table(
        "bill_item_flavor_tags",
        sa.Column("bill_item_id", sa.Uuid(), nullable=False),
        sa.Column("flavor_tag", flavor_tag_enum, nullable=False),
        sa.ForeignKeyConstraint(
            ["bill_item_id"],
            ["bill_items.id"],
            name=op.f("fk_bill_item_flavor_tags_bill_item_id_bill_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "bill_item_id", "flavor_tag", name=op.f("pk_bill_item_flavor_tags")
        ),
    )

    op.create_table(
        "bill_item_dietary_flags",
        sa.Column("bill_item_id", sa.Uuid(), nullable=False),
        sa.Column("dietary_flag", dietary_flag_enum, nullable=False),
        sa.ForeignKeyConstraint(
            ["bill_item_id"],
            ["bill_items.id"],
            name=op.f("fk_bill_item_dietary_flags_bill_item_id_bill_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "bill_item_id", "dietary_flag", name=op.f("pk_bill_item_dietary_flags")
        ),
    )


def downgrade() -> None:
    op.drop_table("bill_item_dietary_flags")
    op.drop_table("bill_item_flavor_tags")
    op.drop_table("bill_items")
    op.drop_table("bills")
    sa.Enum(name="bill_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="base_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="flavor_tag").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="dietary_flag").drop(op.get_bind(), checkfirst=True)
