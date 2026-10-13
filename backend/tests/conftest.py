import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.config import settings
from app.db.base import Base
from app.main import app
from tests.auth_helpers import TEST_JWT_SECRET


@pytest.fixture()
def db_session_factory():
    """An isolated in-memory SQLite DB per test - never touches the real
    Supabase database. StaticPool keeps a single connection alive so every
    session opened against this engine sees the same in-memory data."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        yield testing_session_local
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session_factory, monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", TEST_JWT_SECRET)

    def override_get_db():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # app/services/ocr/pipeline.run_bill_processing_job opens its own DB
    # session directly (deliberately - see that function's docstring), which
    # bypasses FastAPI's dependency_overrides above. Point it at the same
    # in-memory test DB so a bill created through the API during a test
    # doesn't try to reach the real Supabase database.
    import app.services.ocr.pipeline as ocr_pipeline

    monkeypatch.setattr(ocr_pipeline, "SessionLocal", db_session_factory)

    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
