"""Password login: authenticate a stored user and mint an access token."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_access_token
from app.domain.models.exam import User
from app.domain.services import password_service

MAX_FAILED_ATTEMPTS = 10
LOCKOUT_MINUTES = 15

_INVALID = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
)


async def login(db: AsyncSession, *, email: str, password: str) -> dict:
    """Verify credentials and return a token payload.

    Raises 401 on any failure (no user enumeration); 423 when the account is
    temporarily locked after too many failed attempts.
    """
    now = datetime.now(UTC)
    result = await db.execute(select(User).where(User.email == email.strip().lower()))
    user = result.scalar_one_or_none()

    # Same 401 for unknown user, inactive user, or missing hash — no enumeration.
    if user is None or not user.is_active or not user.password_hash:
        raise _INVALID

    if user.password_locked_until is not None and user.password_locked_until > now:
        remaining = int((user.password_locked_until - now).total_seconds() / 60) + 1
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Account locked. Try again in {remaining} minute(s).",
        )

    if not password_service.verify_password(password, user.password_hash):
        user.failed_password_attempts = (user.failed_password_attempts or 0) + 1
        if user.failed_password_attempts >= MAX_FAILED_ATTEMPTS:
            user.password_locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_password_attempts = 0
        await db.commit()
        raise _INVALID

    # Success — reset the failure counter.
    user.failed_password_attempts = 0
    user.password_locked_until = None
    await db.commit()

    token, exp = create_access_token(user_id=user.id, role=user.role, org_id=user.org_id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
        "user_id": str(user.id),
        "org_id": str(user.org_id),
        "expires_at": exp.isoformat(),
    }
