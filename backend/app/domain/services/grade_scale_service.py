"""Grade scale configuration per org (FR-4.28).

A grade scale is a contiguous set of bands covering scores 0-100, each mapping a
score range to a letter grade and GPA points. Orgs may define a custom scale;
when none exists a built-in default (F/D/C/B/A) is used.

Band convention: a band matches a score when ``min_score <= score < max_score``,
except the top band (max_score == 100) which is inclusive of 100. This makes a
score that lands exactly on a boundary resolve to exactly one band.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.exam import GradeScale


@dataclass(frozen=True)
class GradeBand:
    """A single grade band, decoupled from the ORM row."""

    min_score: float
    max_score: float
    letter: str
    gpa_points: float
    sort_order: int


# Built-in default scale used when an org has no custom rows.
DEFAULT_SCALE: tuple[GradeBand, ...] = (
    GradeBand(0.0, 60.0, "F", 0.0, 0),
    GradeBand(60.0, 70.0, "D", 1.0, 1),
    GradeBand(70.0, 80.0, "C", 2.0, 2),
    GradeBand(80.0, 90.0, "B", 3.0, 3),
    GradeBand(90.0, 100.0, "A", 4.0, 4),
)


def _validate_bands(bands: list[GradeBand]) -> list[GradeBand]:
    """Validate a candidate scale: contiguous, non-overlapping, covering 0-100.

    Raises 422 on any gap/overlap or if the scale does not span exactly 0-100.
    Returns the bands sorted by min_score with a normalised sort_order.
    """
    if not bands:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Grade scale must contain at least one band",
        )

    ordered = sorted(bands, key=lambda b: b.min_score)

    for b in ordered:
        if b.min_score >= b.max_score:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Band '{b.letter}' has min_score >= max_score",
            )
        if not b.letter:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Every band must have a non-empty letter",
            )

    if ordered[0].min_score != 0.0 or ordered[-1].max_score != 100.0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Grade scale must cover exactly 0-100",
        )

    for prev, nxt in zip(ordered, ordered[1:], strict=False):
        if prev.max_score != nxt.min_score:
            kind = "overlap" if prev.max_score > nxt.min_score else "gap"
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Grade scale has a {kind} between '{prev.letter}' "
                    f"({prev.max_score}) and '{nxt.letter}' ({nxt.min_score})"
                ),
            )

    return [
        GradeBand(b.min_score, b.max_score, b.letter, b.gpa_points, i)
        for i, b in enumerate(ordered)
    ]


def resolve_letter(
    score: float | None, bands: tuple[GradeBand, ...] | list[GradeBand]
) -> str | None:
    """Return the letter grade for a score given a scale, or None if score is None."""
    if score is None:
        return None
    for b in bands:
        if b.min_score <= score < b.max_score or (b.max_score >= 100.0 and score >= b.min_score):
            return b.letter
    return None


async def get_scale(db: AsyncSession, *, org_id: uuid.UUID) -> list[GradeBand]:
    """Return the org's persisted scale, or the default when none is configured."""
    result = await db.execute(
        select(GradeScale).where(GradeScale.org_id == org_id).order_by(GradeScale.sort_order.asc())
    )
    rows = result.scalars().all()
    if not rows:
        return list(DEFAULT_SCALE)
    return [GradeBand(r.min_score, r.max_score, r.letter, r.gpa_points, r.sort_order) for r in rows]


async def put_scale(
    db: AsyncSession, *, org_id: uuid.UUID, bands: list[GradeBand]
) -> list[GradeBand]:
    """Atomically replace the org's entire scale with the supplied bands."""
    validated = _validate_bands(bands)

    await db.execute(delete(GradeScale).where(GradeScale.org_id == org_id))
    for b in validated:
        db.add(
            GradeScale(
                org_id=org_id,
                min_score=b.min_score,
                max_score=b.max_score,
                letter=b.letter,
                gpa_points=b.gpa_points,
                sort_order=b.sort_order,
            )
        )
    await db.commit()
    return validated
