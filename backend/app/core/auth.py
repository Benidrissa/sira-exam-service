"""JWT verification — validates tokens issued by Sira (shared HS256 secret).

The exam service never issues its own tokens. It only validates Sira JWTs
and reads user_id, role, org_id from claims. No database lookup required.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import HTTPException, status

from app.core.config import settings

# Access tokens are valid for 24h, matching the previous dev-token lifetime.
ACCESS_TOKEN_TTL = timedelta(hours=24)


def create_access_token(
    *, user_id: uuid.UUID | str, role: str, org_id: uuid.UUID | str
) -> tuple[str, datetime]:
    """Mint a JWT with the exact claims verify_sira_token reads.

    Returns (token, expires_at). Signed with the same secret/algorithm the app
    already validates, so every existing endpoint accepts it unchanged.
    """
    exp = datetime.now(UTC) + ACCESS_TOKEN_TTL
    payload = {
        "sub": str(user_id),
        "role": role,
        "org_id": str(org_id),
        "exp": exp,
        "iat": datetime.now(UTC),
        "iss": "sira-exam",
    }
    token = jwt.encode(payload, settings.sira_jwt_secret, algorithm=settings.jwt_algorithm)
    return token, exp


class AuthenticatedUser:
    def __init__(self, user_id: str, role: str, org_id: str | None = None) -> None:
        self.user_id = user_id
        self.role = role
        self.org_id = org_id

    @property
    def is_admin(self) -> bool:
        return self.role in ("admin", "sub_admin")

    @property
    def is_teacher(self) -> bool:
        return self.role in ("admin", "sub_admin", "expert")


def verify_sira_token(token: str) -> AuthenticatedUser:
    """Decode and validate a Sira-issued JWT. Raises 401 on any failure."""
    try:
        payload = jwt.decode(
            token,
            settings.sira_jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id: str | None = payload.get("sub")
    role: str | None = payload.get("role")
    if not user_id or not role:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token claims")

    return AuthenticatedUser(
        user_id=user_id,
        role=role,
        org_id=payload.get("org_id"),
    )
