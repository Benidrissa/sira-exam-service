"""Dev-only endpoints — token minting for staging UAT.

Only registered when settings.debug = True. Never exposed in production.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(prefix="/dev", tags=["dev"])

# Fixed test identities matching conftest.py fixtures
_TEACHER_ID = uuid.UUID("cccccccc-0000-0000-0000-000000000001")
_STUDENT_ID = uuid.UUID("dddddddd-0000-0000-0000-000000000002")
_ORG_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")


class DevTokenResponse(BaseModel):
    access_token: str
    role: str
    user_id: str
    org_id: str
    expires_at: str


@router.get("/tokens", response_model=DevTokenResponse)
async def mint_dev_token(role: str = "expert") -> DevTokenResponse:
    """Return a signed JWT for staging UAT.

    role=expert  → teacher (can create banks, validate questions, grade)
    role=user    → student (can start attempts, submit answers)
    """
    if role not in ("expert", "user", "admin", "sub_admin"):
        role = "expert"

    user_id = _TEACHER_ID if role in ("expert", "admin", "sub_admin") else _STUDENT_ID
    exp = datetime.now(UTC) + timedelta(hours=24)

    payload = {
        "sub": str(user_id),
        "role": role,
        "org_id": str(_ORG_ID),
        "exp": exp,
        "iat": datetime.now(UTC),
        "iss": "sira-exam-dev",
    }
    token = jwt.encode(payload, settings.sira_jwt_secret, algorithm=settings.jwt_algorithm)

    return DevTokenResponse(
        access_token=token,
        role=role,
        user_id=str(user_id),
        org_id=str(_ORG_ID),
        expires_at=exp.isoformat(),
    )
