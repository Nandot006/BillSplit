import uuid
from datetime import datetime, timedelta, timezone

import jwt

TEST_JWT_SECRET = "test-secret-for-pytest-only"


def make_token(
    user_id: uuid.UUID, email: str = "test@example.com", display_name: str | None = None
) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "aud": "authenticated",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "user_metadata": {"display_name": display_name} if display_name else {},
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


def auth_headers(user_id: uuid.UUID, **kwargs) -> dict:
    return {"Authorization": f"Bearer {make_token(user_id, **kwargs)}"}
