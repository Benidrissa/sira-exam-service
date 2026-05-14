from app.core.database import Base
from app.domain.models.exam import (  # noqa: F401
    DissertationAnswer,
    ExamAttempt,
    ExamBank,
    ExamQuestion,
    ExamScenario,
    ExamSource,
    ExamTest,
)

__all__ = ["Base"]
