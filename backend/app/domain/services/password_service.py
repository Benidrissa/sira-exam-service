"""Password hashing + verification (bcrypt)."""

from __future__ import annotations

import bcrypt

MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    """Return a bcrypt hash of the plaintext password."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Check a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def validate_password(password: str) -> None:
    """Raise ValueError if the password is too weak."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
