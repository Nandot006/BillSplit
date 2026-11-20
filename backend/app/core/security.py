import uuid
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.user import User

_bearer_scheme = HTTPBearer(auto_error=False)

# Supabase signs user session JWTs one of two ways, depending on the project:
#   - legacy: HS256 with the project's shared JWT secret (SUPABASE_JWT_SECRET)
#   - current: asymmetric signing keys (ES256 or RS256), whose public halves
#     are published at <SUPABASE_URL>/auth/v1/.well-known/jwks.json
# We accept both, picking the path from the token header's `alg`, so the
# backend works whichever mode the Supabase project is in (and keeps working
# through a migration from one to the other).
_ASYMMETRIC_ALGORITHMS = ("ES256", "RS256")


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


@lru_cache(maxsize=1)
def _jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    # PyJWKClient caches fetched keys in-process, so this is one HTTP call
    # per backend process (plus a refetch whenever an unknown `kid` shows up,
    # e.g. after a key rotation), not one per request.
    return jwt.PyJWKClient(jwks_url, cache_keys=True)


def _decode_with_shared_secret(token: str) -> dict:
    if not settings.SUPABASE_JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SUPABASE_JWT_SECRET is not configured on the backend.",
        )
    return jwt.decode(
        token,
        settings.SUPABASE_JWT_SECRET,
        algorithms=["HS256"],
        audience="authenticated",
    )


def _decode_with_jwks(token: str, algorithm: str) -> dict:
    if not settings.SUPABASE_URL:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SUPABASE_URL is not configured on the backend.",
        )
    base_url = settings.SUPABASE_URL.rstrip("/")
    try:
        signing_key = _jwks_client(f"{base_url}/auth/v1/.well-known/jwks.json")
        key = signing_key.get_signing_key_from_jwt(token).key
    except jwt.PyJWKClientError as exc:
        raise _unauthorized("Could not find a matching signing key for this token.") from exc
    return jwt.decode(
        token,
        key,
        algorithms=[algorithm],
        audience="authenticated",
        issuer=f"{base_url}/auth/v1",
    )


def _decode_supabase_jwt(token: str) -> dict:
    try:
        algorithm = jwt.get_unverified_header(token).get("alg")
    except jwt.InvalidTokenError:
        raise _unauthorized("Invalid authentication token.")

    try:
        if algorithm == "HS256":
            return _decode_with_shared_secret(token)
        if algorithm in _ASYMMETRIC_ALGORITHMS:
            return _decode_with_jwks(token, algorithm)
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Token has expired.")
    except jwt.InvalidTokenError:
        raise _unauthorized("Invalid authentication token.")

    raise _unauthorized("Unsupported token signing algorithm.")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Verifies the Supabase-issued JWT the client attaches as
    `Authorization: Bearer <token>` (Web/Mobile get this token straight from
    the Supabase Auth SDK - this backend never issues or checks passwords
    itself). On first sight of a given Supabase user id, lazily creates a
    matching local `users` row so the rest of the schema has something to
    foreign-key against.
    """
    if credentials is None:
        raise _unauthorized("Missing bearer token.")

    claims = _decode_supabase_jwt(credentials.credentials)

    try:
        user_id = uuid.UUID(claims["sub"])
    except (KeyError, ValueError):
        raise _unauthorized("Token missing a valid subject claim.")

    user = db.get(User, user_id)
    user_metadata = claims.get("user_metadata") or {}
    if user is None:
        user = User(
            id=user_id,
            email=claims.get("email"),
            display_name=user_metadata.get("display_name"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user
