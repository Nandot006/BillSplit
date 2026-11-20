"""enable row level security on every table

Supabase publishes everything in the `public` schema through its REST API
(PostgREST), reachable with the project's anon key - and that key ships in
the web app's JavaScript, so anyone has it. With RLS off, anyone could read
or edit every group, person and bill through that API, bypassing all of
this backend's access checks (CLAUDE.md SS9).

Turning RLS on with *no* policies closes that door completely: the anon and
authenticated roles see nothing. This backend is unaffected - it connects as
the `postgres` role, which owns these tables, and table owners bypass RLS.
On a plain Postgres (local dev, tests) this is harmless.

Any table added by a later migration needs the same ENABLE ROW LEVEL
SECURITY line (see CLAUDE.md SS11).

Revision ID: c41f8e7a9d02
Revises: a7c3e9d21b54
Create Date: 2026-11-20 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c41f8e7a9d02"
down_revision: str | Sequence[str] | None = "a7c3e9d21b54"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "alembic_version",
    "users",
    "groups",
    "people",
    "person_taxonomy_scores",
    "bills",
    "bill_items",
    "bill_item_flavor_tags",
    "bill_item_dietary_flags",
    "bill_item_assignments",
    "prediction_feedback",
    "payer_history",
    "splits",
    "bill_participants",
)


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
