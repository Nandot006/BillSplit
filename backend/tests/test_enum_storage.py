"""Regression test for a production-only bug found in end-to-end testing
(2026-11-20): the migrations create Postgres enum types from the enum
*values* ("needs_review", "drink-non-alcoholic"), but the models stored
enum *names* ("NEEDS_REVIEW"), so every insert of an enum column failed on
Postgres with `invalid input value for enum`. The rest of this suite runs on
SQLite, which stores enums as plain text and can't see that mismatch - so
this test checks the mapping itself."""

import importlib
import pkgutil
import re
from pathlib import Path

import sqlalchemy as sa

import app.models
from app.db.base import Base

MIGRATIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _all_enum_columns():
    for module in pkgutil.iter_modules(app.models.__path__):
        importlib.import_module(f"app.models.{module.name}")
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, sa.Enum):
                yield table.name, column


def test_every_enum_column_stores_values_not_names():
    columns = list(_all_enum_columns())
    assert columns, "expected some enum columns"
    for table, column in columns:
        enum_cls = column.type.enum_class
        assert enum_cls is not None
        expected = [member.value for member in enum_cls]
        assert list(column.type.enums) == expected, (
            f"{table}.{column.name} would store {list(column.type.enums)[:2]}..., "
            f"but the Postgres enum holds {expected[:2]}... - add values_callable=enum_values"
        )


def test_model_enum_labels_match_the_migrations():
    """The labels each migration creates must be exactly what the model
    sends, for every named Postgres enum type."""
    migration_source = "\n".join(p.read_text() for p in MIGRATIONS.glob("*.py"))
    for _table, column in _all_enum_columns():
        for label in column.type.enums:
            assert re.search(rf'["\']{re.escape(label)}["\']', migration_source) or (
                # some migrations build their label lists from the enum classes
                f"{column.type.enum_class.__name__}"
                in migration_source
            ), f"enum label {label!r} ({column.type.name}) not found in any migration"
