"""Shared grade computation helpers (FR-4.27, FR-4.31, FR-4.32).

This is the single source of truth for:
  * the FR-4.13 feedback-availability rule,
  * the weighted term-average formula, and
  * letter-grade resolution against the org's grade scale.

Keeping these here prevents the term summary, the student term page, and
term finalisation from drifting apart.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services import grade_scale_service


def compute_feedback_available(
    *, show_feedback: bool, closes_ats: Iterable[dt | None], now: dt | None = None
) -> bool:
    """FR-4.13: feedback is available when the test enables it OR any assignment
    window has closed."""
    if show_feedback:
        return True
    now = now or dt.now(tz=UTC)
    return any(c is not None and c.astimezone(UTC) < now for c in closes_ats)


@dataclass(frozen=True)
class ExamGrade:
    """One exam's contribution to a student's term average."""

    score: float | None
    weight: float
    submitted: bool
    dispensed: bool
    feedback_available: bool

    @property
    def counts_toward_average(self) -> bool:
        """An exam contributes only when submitted, not dispensed, feedback is
        available, and a score exists."""
        return (
            self.submitted
            and not self.dispensed
            and self.feedback_available
            and self.score is not None
        )


def weighted_average(exams: Sequence[ExamGrade]) -> float | None:
    """Σ(score × weight) / Σ(weight) over contributing exams; None if none."""
    numerator = 0.0
    denominator = 0.0
    for exam in exams:
        if not exam.counts_toward_average:
            continue
        assert exam.score is not None  # guaranteed by counts_toward_average
        numerator += exam.score * exam.weight
        denominator += exam.weight
    if denominator == 0:
        return None
    return numerator / denominator


async def resolve_letter_grade(
    db: AsyncSession, *, org_id: uuid.UUID, score: float | None
) -> str | None:
    """Resolve a score to a letter using the org's scale (default when none)."""
    if score is None:
        return None
    bands = await grade_scale_service.get_scale(db, org_id=org_id)
    return grade_scale_service.resolve_letter(score, bands)
