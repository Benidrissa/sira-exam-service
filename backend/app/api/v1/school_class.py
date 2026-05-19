"""School class management API — roster, enrollment, test scheduling (FR-4.1–FR-4.5)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import DB, TeacherUser
from app.domain.services import school_class_service
from app.schemas.exam import (
    ClassMemberCreate,
    ClassMemberResponse,
    SchoolClassCreate,
    SchoolClassDetailResponse,
    SchoolClassResponse,
    SchoolClassUpdate,
    TestAssignmentCreate,
    TestAssignmentResponse,
    TestAssignmentUpdate,
)

router = APIRouter(prefix="/exam", tags=["school-class"])


def _org(user: TeacherUser) -> uuid.UUID:
    return uuid.UUID(user.org_id) if user.org_id else uuid.UUID(int=0)


def _uid(user: TeacherUser) -> uuid.UUID:
    return uuid.UUID(user.user_id)


# ---------------------------------------------------------------------------
# SchoolClass CRUD (FR-4.1)
# ---------------------------------------------------------------------------


@router.post("/classes", response_model=SchoolClassResponse, status_code=status.HTTP_201_CREATED)
async def create_school_class(
    data: SchoolClassCreate,
    db: DB,
    user: TeacherUser,
) -> SchoolClassResponse:
    """Create a new school class (FR-4.1)."""
    school_class = await school_class_service.create_class(
        db,
        org_id=_org(user),
        created_by=_uid(user),
        name=data.name,
        academic_year=data.academic_year,
    )
    return SchoolClassResponse.model_validate(school_class)


@router.get("/classes", response_model=list[SchoolClassResponse])
async def list_school_classes(
    db: DB,
    user: TeacherUser,
    academic_year: str | None = None,
) -> list[SchoolClassResponse]:
    """List all school classes for this org (FR-4.1)."""
    classes = await school_class_service.list_classes(
        db,
        org_id=_org(user),
        academic_year=academic_year,
    )
    return [SchoolClassResponse.model_validate(c) for c in classes]


@router.get("/classes/{class_id}", response_model=SchoolClassDetailResponse)
async def get_school_class(
    class_id: uuid.UUID,
    db: DB,
    user: TeacherUser,
) -> SchoolClassDetailResponse:
    """Get a school class with its member list (FR-4.1)."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.domain.models.exam import SchoolClass

    result = await db.execute(
        select(SchoolClass)
        .options(selectinload(SchoolClass.members))
        .where(SchoolClass.id == class_id, SchoolClass.org_id == _org(user))
    )
    school_class = result.scalar_one_or_none()
    if school_class is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="SchoolClass not found")
    return SchoolClassDetailResponse.model_validate(school_class)


@router.patch("/classes/{class_id}", response_model=SchoolClassResponse)
async def update_school_class(
    class_id: uuid.UUID,
    data: SchoolClassUpdate,
    db: DB,
    user: TeacherUser,
) -> SchoolClassResponse:
    """Partially update a school class (FR-4.1)."""
    school_class = await school_class_service.update_class(
        db,
        class_id=class_id,
        org_id=_org(user),
        name=data.name,
        academic_year=data.academic_year,
    )
    return SchoolClassResponse.model_validate(school_class)


@router.delete("/classes/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_school_class(
    class_id: uuid.UUID,
    db: DB,
    user: TeacherUser,
) -> None:
    """Delete a school class (only if no members enrolled) (FR-4.1)."""
    await school_class_service.delete_class(db, class_id=class_id, org_id=_org(user))


# ---------------------------------------------------------------------------
# ClassMember enrollment (FR-4.2)
# ---------------------------------------------------------------------------


@router.post(
    "/classes/{class_id}/members",
    response_model=ClassMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def enroll_student(
    class_id: uuid.UUID,
    data: ClassMemberCreate,
    db: DB,
    user: TeacherUser,
) -> ClassMemberResponse:
    """Enroll a student in a school class (FR-4.2)."""
    member = await school_class_service.enroll_student(
        db,
        class_id=class_id,
        org_id=_org(user),
        user_id=data.user_id,
        added_by=_uid(user),
    )
    return ClassMemberResponse.model_validate(member)


@router.get("/classes/{class_id}/members", response_model=list[ClassMemberResponse])
async def list_class_members(
    class_id: uuid.UUID,
    db: DB,
    user: TeacherUser,
) -> list[ClassMemberResponse]:
    """List all members of a school class (FR-4.2)."""
    members = await school_class_service.list_members(
        db,
        class_id=class_id,
        org_id=_org(user),
    )
    return [ClassMemberResponse.model_validate(m) for m in members]


@router.delete(
    "/classes/{class_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_class_member(
    class_id: uuid.UUID,
    user_id: uuid.UUID,
    db: DB,
    user: TeacherUser,
) -> None:
    """Remove a student from a school class (FR-4.2)."""
    await school_class_service.remove_member(
        db,
        class_id=class_id,
        org_id=_org(user),
        user_id=user_id,
    )


# ---------------------------------------------------------------------------
# TestAssignment scheduling (FR-4.3–FR-4.5)
# ---------------------------------------------------------------------------


@router.post(
    "/tests/{test_id}/assignments",
    response_model=TestAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_test_assignment(
    test_id: uuid.UUID,
    data: TestAssignmentCreate,
    db: DB,
    user: TeacherUser,
) -> TestAssignmentResponse:
    """Assign an exam test to a school class with a time window (FR-4.3)."""
    assignment = await school_class_service.create_assignment(
        db,
        test_id=test_id,
        class_id=data.class_id,
        org_id=_org(user),
        released_at=data.released_at,
        closes_at=data.closes_at,
        quarter=data.quarter,
        assigned_by=_uid(user),
    )
    return TestAssignmentResponse.model_validate(assignment)


@router.get("/tests/{test_id}/assignments", response_model=list[TestAssignmentResponse])
async def list_test_assignments(
    test_id: uuid.UUID,
    db: DB,
    user: TeacherUser,
) -> list[TestAssignmentResponse]:
    """List all assignments for a test (FR-4.4)."""
    assignments = await school_class_service.list_assignments(
        db,
        test_id=test_id,
        org_id=_org(user),
    )
    return [TestAssignmentResponse.model_validate(a) for a in assignments]


@router.patch(
    "/tests/{test_id}/assignments/{assignment_id}",
    response_model=TestAssignmentResponse,
)
async def update_test_assignment(
    test_id: uuid.UUID,
    assignment_id: uuid.UUID,
    data: TestAssignmentUpdate,
    db: DB,
    user: TeacherUser,
) -> TestAssignmentResponse:
    """Update a test assignment window or quarter (FR-4.4)."""
    assignment = await school_class_service.update_assignment(
        db,
        assignment_id=assignment_id,
        org_id=_org(user),
        released_at=data.released_at,
        closes_at=data.closes_at,
        quarter=data.quarter,
    )
    return TestAssignmentResponse.model_validate(assignment)


@router.delete(
    "/tests/{test_id}/assignments/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_test_assignment(
    test_id: uuid.UUID,
    assignment_id: uuid.UUID,
    db: DB,
    user: TeacherUser,
) -> None:
    """Delete a test assignment (only if no attempts exist) (FR-4.5)."""
    await school_class_service.delete_assignment(
        db,
        assignment_id=assignment_id,
        org_id=_org(user),
    )
