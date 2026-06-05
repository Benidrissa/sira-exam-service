"""Auth request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    # A login identifier, not a signup field — keep it a plain string so reserved
    # TLDs (e.g. *.test) and other valid-but-unusual addresses can authenticate.
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: str
    org_id: str
    expires_at: str
