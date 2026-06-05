"""Unit tests for real password authentication."""

from __future__ import annotations

import uuid
from datetime import UTC, timedelta
from datetime import datetime as dt
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.domain.models.exam import User
from app.domain.services import auth_service, password_service
from app.schemas.auth import LoginRequest


def test_login_request_accepts_reserved_tld() -> None:
    # *.test is a reserved TLD that strict EmailStr rejects; login must accept it.
    req = LoginRequest(email="teacher@sira.test", password="x")
    assert req.email == "teacher@sira.test"


ORG = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
UID = uuid.UUID("cccccccc-0000-0000-0000-000000000001")


# --- password_service -------------------------------------------------------


def test_hash_is_not_plaintext_and_verifies() -> None:
    h = password_service.hash_password("s3cret-passw0rd")
    assert h != "s3cret-passw0rd"
    assert password_service.verify_password("s3cret-passw0rd", h) is True
    assert password_service.verify_password("wrong", h) is False


def test_verify_handles_garbage_hash() -> None:
    assert password_service.verify_password("x", "not-a-bcrypt-hash") is False


def test_validate_password_min_length() -> None:
    with pytest.raises(ValueError):
        password_service.validate_password("short")
    password_service.validate_password("longenough")


# --- auth_service.login -----------------------------------------------------


def _db(user: User | None) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


def _user(**kw) -> User:
    defaults = dict(
        id=UID,
        email="teacher@sira.test",
        name="T",
        password_hash=password_service.hash_password("Correct-Horse-1"),
        role="expert",
        org_id=ORG,
        is_active=True,
        failed_password_attempts=0,
        password_locked_until=None,
    )
    defaults.update(kw)
    return User(**defaults)


async def test_login_success_returns_valid_token() -> None:
    db = _db(_user())
    out = await auth_service.login(db, email="Teacher@Sira.test", password="Correct-Horse-1")
    assert out["role"] == "expert"
    assert out["user_id"] == str(UID)
    assert out["org_id"] == str(ORG)
    payload = jwt.decode(
        out["access_token"], settings.sira_jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    assert payload["sub"] == str(UID)
    assert payload["role"] == "expert"
    assert payload["org_id"] == str(ORG)
    db.commit.assert_awaited()


async def test_login_wrong_password_401_and_counts() -> None:
    user = _user()
    db = _db(user)
    with pytest.raises(HTTPException) as exc:
        await auth_service.login(db, email="teacher@sira.test", password="nope")
    assert exc.value.status_code == 401
    assert user.failed_password_attempts == 1


async def test_login_unknown_email_401() -> None:
    db = _db(None)
    with pytest.raises(HTTPException) as exc:
        await auth_service.login(db, email="ghost@sira.test", password="whatever")
    assert exc.value.status_code == 401


async def test_login_inactive_user_401() -> None:
    db = _db(_user(is_active=False))
    with pytest.raises(HTTPException) as exc:
        await auth_service.login(db, email="teacher@sira.test", password="Correct-Horse-1")
    assert exc.value.status_code == 401


async def test_login_locked_account_423() -> None:
    locked = _user(password_locked_until=dt.now(tz=UTC) + timedelta(minutes=5))
    db = _db(locked)
    with pytest.raises(HTTPException) as exc:
        await auth_service.login(db, email="teacher@sira.test", password="Correct-Horse-1")
    assert exc.value.status_code == 423


async def test_login_locks_after_max_failures() -> None:
    user = _user(failed_password_attempts=auth_service.MAX_FAILED_ATTEMPTS - 1)
    db = _db(user)
    with pytest.raises(HTTPException):
        await auth_service.login(db, email="teacher@sira.test", password="nope")
    assert user.password_locked_until is not None
