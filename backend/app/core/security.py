import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.user import User

_bearer_scheme = HTTPBearer(auto_error=False)


def _decode_supabase_jwt(token: str) -> dict:
    if not settings.SUPABASE_JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SUPABASE_JWT_SECRET is not configured on the backend.",
        )
    try:
        return jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token."
        )


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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token."
        )

    claims = _decode_supabase_jwt(credentials.credentials)

    try:
        user_id = uuid.UUID(claims["sub"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing a valid subject claim."
        )

    user = db.get(User, user_id)
    if user is None:
        user_metadata = claims.get("user_metadata") or {}
        user = User(
            id=user_id,
            email=claims.get("email"),
            display_name=user_metadata.get("display_name"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user
