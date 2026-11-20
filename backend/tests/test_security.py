"""Auth token verification (app/core/security.py) and CORS (app/main.py).

The rest of the suite authenticates with HS256 tokens signed by the shared
test secret (tests/auth_helpers.py). These tests cover the other path: a
Supabase project on asymmetric signing keys, whose tokens are ES256 and are
verified against the project's JWKS endpoint.
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

import app.core.security as security
from app.core.config import settings

SUPABASE_URL = "https://example-project.supabase.co"


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKClient:
    def __init__(self, public_key):
        self._public_key = public_key

    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(self._public_key)


@pytest.fixture()
def es256_keys(monkeypatch):
    private_key = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setattr(settings, "SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setattr(
        security, "_jwks_client", lambda url: _FakeJWKClient(private_key.public_key())
    )
    return private_key


def _es256_token(private_key, user_id: uuid.UUID, **overrides) -> str:
    payload = {
        "sub": str(user_id),
        "email": "es@example.com",
        "aud": "authenticated",
        "iss": f"{SUPABASE_URL}/auth/v1",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "user_metadata": {"display_name": "Esther"},
    }
    payload.update(overrides)
    return jwt.encode(payload, private_key, algorithm="ES256", headers={"kid": "test-kid"})


def test_es256_token_verified_via_jwks(client, es256_keys):
    user_id = uuid.uuid4()
    token = _es256_token(es256_keys, user_id)
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["id"] == str(user_id)
    assert response.json()["display_name"] == "Esther"


def test_es256_token_with_wrong_issuer_rejected(client, es256_keys):
    token = _es256_token(es256_keys, uuid.uuid4(), iss="https://someone-else.supabase.co/auth/v1")
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_es256_token_signed_by_another_key_rejected(client, es256_keys):
    other_key = ec.generate_private_key(ec.SECP256R1())
    token = _es256_token(other_key, uuid.uuid4())
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_expired_es256_token_rejected(client, es256_keys):
    token = _es256_token(
        es256_keys, uuid.uuid4(), exp=datetime.now(timezone.utc) - timedelta(minutes=1)
    )
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Token has expired."


def test_unsupported_algorithm_rejected(client):
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "aud": "authenticated"}, "x" * 64, algorithm="HS512"
    )
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_garbage_token_rejected(client):
    response = client.get("/api/v1/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


def test_cors_preflight_allows_configured_origin(client):
    response = client.options(
        "/api/v1/groups",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_preflight_rejects_unknown_origin(client):
    response = client.options(
        "/api/v1/groups",
        headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in response.headers


def test_database_url_postgres_scheme_normalized():
    from app.core.config import Settings

    s = Settings(DATABASE_URL="postgres://u:p@host:5432/db")
    assert s.DATABASE_URL == "postgresql://u:p@host:5432/db"
