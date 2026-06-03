"""Unit tests for grade scale configuration (FR-4.28).

Validation, default-scale fallback, and letter resolution are pure functions;
the atomic replace is exercised against a mocked AsyncSession.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.domain.services import grade_scale_service as svc
from app.domain.services.grade_scale_service import DEFAULT_SCALE, GradeBand

ORG = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")


def _custom_pass_fail() -> list[GradeBand]:
    return [
        GradeBand(0.0, 50.0, "FAIL", 0.0, 0),
        GradeBand(50.0, 100.0, "PASS", 4.0, 1),
    ]


# --- validation -------------------------------------------------------------


def test_validate_accepts_contiguous_full_cover() -> None:
    out = svc._validate_bands(_custom_pass_fail())
    assert [b.letter for b in out] == ["FAIL", "PASS"]
    assert [b.sort_order for b in out] == [0, 1]


def test_validate_rejects_gap() -> None:
    bands = [GradeBand(0.0, 40.0, "F", 0.0, 0), GradeBand(50.0, 100.0, "P", 4.0, 1)]
    with pytest.raises(HTTPException) as exc:
        svc._validate_bands(bands)
    assert exc.value.status_code == 422
    assert "gap" in exc.value.detail


def test_validate_rejects_overlap() -> None:
    bands = [GradeBand(0.0, 60.0, "F", 0.0, 0), GradeBand(50.0, 100.0, "P", 4.0, 1)]
    with pytest.raises(HTTPException) as exc:
        svc._validate_bands(bands)
    assert exc.value.status_code == 422
    assert "overlap" in exc.value.detail


def test_validate_rejects_not_covering_0_100() -> None:
    bands = [GradeBand(10.0, 100.0, "X", 0.0, 0)]
    with pytest.raises(HTTPException) as exc:
        svc._validate_bands(bands)
    assert exc.value.status_code == 422
    assert "0-100" in exc.value.detail


def test_validate_rejects_inverted_band() -> None:
    bands = [GradeBand(0.0, 100.0, "A", 0.0, 0), GradeBand(100.0, 50.0, "B", 0.0, 1)]
    with pytest.raises(HTTPException):
        svc._validate_bands(bands)


def test_validate_rejects_empty() -> None:
    with pytest.raises(HTTPException) as exc:
        svc._validate_bands([])
    assert exc.value.status_code == 422


def test_validate_sorts_unordered_input() -> None:
    bands = [GradeBand(50.0, 100.0, "P", 4.0, 9), GradeBand(0.0, 50.0, "F", 0.0, 9)]
    out = svc._validate_bands(bands)
    assert [b.letter for b in out] == ["F", "P"]
    assert [b.sort_order for b in out] == [0, 1]


# --- resolve_letter ---------------------------------------------------------


@pytest.mark.parametrize(
    "score,letter",
    [(0, "F"), (59.9, "F"), (60, "D"), (75, "C"), (80, "B"), (89.99, "B"), (90, "A"), (100, "A")],
)
def test_resolve_letter_default_boundaries(score: float, letter: str) -> None:
    assert svc.resolve_letter(score, DEFAULT_SCALE) == letter


def test_resolve_letter_none_score() -> None:
    assert svc.resolve_letter(None, DEFAULT_SCALE) is None


def test_resolve_letter_top_band_inclusive_of_100() -> None:
    assert svc.resolve_letter(100, _custom_pass_fail()) == "PASS"


# --- get_scale / put_scale --------------------------------------------------


@pytest.mark.asyncio
async def test_get_scale_returns_default_when_none() -> None:
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=result)

    bands = await svc.get_scale(db, org_id=ORG)
    assert [b.letter for b in bands] == ["F", "D", "C", "B", "A"]


@pytest.mark.asyncio
async def test_put_scale_validates_then_replaces() -> None:
    db = MagicMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    out = await svc.put_scale(db, org_id=ORG, bands=_custom_pass_fail())

    # one delete (replace) + two inserts + commit
    assert db.execute.await_count == 1
    assert db.add.call_count == 2
    db.commit.assert_awaited_once()
    assert [b.letter for b in out] == ["FAIL", "PASS"]


@pytest.mark.asyncio
async def test_put_scale_rejects_invalid_before_delete() -> None:
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()

    bad = [GradeBand(0.0, 40.0, "F", 0.0, 0)]  # does not reach 100
    with pytest.raises(HTTPException):
        await svc.put_scale(db, org_id=ORG, bands=bad)

    db.execute.assert_not_awaited()  # nothing deleted on invalid input
    db.commit.assert_not_awaited()
