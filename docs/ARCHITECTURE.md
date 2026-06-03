# Architecture — Sira Exam Service

> See [SRS.md](SRS.md) for functional requirements. See [USER_STORIES.md](USER_STORIES.md) for UAT scenarios.

---

## System Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Sira Platform (shared infra)                                                │
│                                                                              │
│  ┌─────────────┐    JWT     ┌──────────────────────────────────────────────┐ │
│  │  Sira Auth  │──────────▶│           Sira Exam Service                  │ │
│  │  Service    │            │                                              │ │
│  └─────────────┘            │  ┌────────────────┐  ┌───────────────────┐  │ │
│                              │  │  FastAPI       │  │  Next.js 16       │  │ │
│  ┌─────────────┐            │  │  :8001         │  │  :3001            │  │ │
│  │  PostgreSQL │◀──────────▶│  │  (REST API)    │  │  (Frontend)       │  │ │
│  │  sira_db    │            │  └───────┬────────┘  └───────────────────┘  │ │
│  │  schema:    │            │          │                                   │ │
│  │  exam_svc   │            │  ┌───────▼────────┐                         │ │
│  └─────────────┘            │  │  Celery Worker │                         │ │
│                              │  │  (async tasks) │                         │ │
│  ┌─────────────┐            │  └───────┬────────┘                         │ │
│  │  Redis :6379│◀──────────▶│          │                                   │ │
│  │  prefix:    │            │  ┌───────▼────────┐                         │ │
│  │  exam:*     │            │  │  Anthropic API │                         │ │
│  └─────────────┘            │  │  claude-sonnet │                         │ │
│                              │  └────────────────┘                         │ │
│  ┌─────────────┐            │                                              │ │
│  │  MinIO      │◀──────────▶│  Phase 2 only:                               │ │
│  │  bucket:    │            │  ┌────────────────┐                         │ │
│  │  exam-evid. │            │  │  WebSocket     │                         │ │
│  └─────────────┘            │  │  signaling     │                         │ │
│                              │  └────────────────┘                         │ │
└──────────────────────────────┴──────────────────────────────────────────────┘
```

---

## Component Breakdown

### Backend — FastAPI (`backend/`)
| File | Responsibility |
|------|---------------|
| `app/main.py` | FastAPI app factory, CORS, lifespan |
| `app/api/v1/exam.py` | Exam, attempt, submission, review, and complaint endpoints |
| `app/api/v1/school_class.py` | SchoolClass CRUD + ClassMember enrollment + TestAssignment scheduling (Phase 4) |
| `app/api/deps.py` | Dependency injection (DB session, current user from JWT) |
| `app/core/auth.py` | JWT validation against `SIRA_JWT_SECRET` |
| `app/core/config.py` | Settings via pydantic-settings |
| `app/core/database.py` | SQLAlchemy async engine + session factory |
| `app/core/redis.py` | Redis client (aioredis) |
| `app/domain/models/exam.py` | SQLAlchemy ORM models (Phase 1 + Phase 4 additions) |
| `app/domain/services/` | Business logic services |
| `app/domain/services/school_class_service.py` | SchoolClass, ClassMember, TestAssignment CRUD (Phase 4) |
| `app/domain/services/exam_submission_service.py` | Teacher submission list/review/validate + student history/review (Phase 4) |
| `app/domain/services/score_complaint_service.py` | Score complaint filing + teacher resolution (Phase 4) |
| `app/infrastructure/storage.py` | MinIO/S3 client (aiobotocore) |
| `app/tasks/celery_app.py` | Celery config (Redis broker + backend) |
| `app/tasks/extraction.py` | `extract_exam_source_task` |

### Frontend — Next.js 16 (`frontend/`)
| Path | Responsibility |
|------|---------------|
| `src/app/[locale]/` | i18n routing (next-intl, EN/FR) |
| `src/app/[locale]/create/` | Exam creation wizard |
| `src/lib/api.ts` | HTTP client (fetch wrapper for FastAPI) |
| `src/middleware.ts` | next-intl locale detection middleware |
| `messages/{en,fr}.json` | Translation strings |

### Celery Tasks
| Task | Trigger | Description |
|------|---------|-------------|
| `extract_exam_source_task` | POST /sources | PyMuPDF → raw_text, char_count |
| `generate_exam_task` | POST /generate | Claude forced tool use → scenarios + questions |
| `ai_correct_dissertation_task` | Attempt submit | Claude grading → ai_score, ai_feedback |
| `analyze_snapshot_task` (P2) | Snapshot recorded | Claude Vision → violation flags |
| `check_heartbeat_task` (P2) | Celery beat 30s | Detect dead sessions |
| `finalize_session_task` (P2) | Session end | SHA-256 evidence digest |

---

## Data Models

### Phase 1

```
ExamBank
  id, org_id, created_by, title, description
  status: draft | review | published | archived
  generation_error: str | null

ExamSource
  id, bank_id, filename, minio_key
  raw_text, char_count
  status: pending | done | error

ExamScenario
  id, bank_id, title, context_text, order_index
  generation_metadata: jsonb

ExamQuestion
  id, scenario_id, type: mcq | dissertation
  stem, options: jsonb (MCQ), model_answer, rubric: jsonb
  correct_option (MCQ), points, validated: bool

ExamTest
  id, bank_id, title, time_limit_minutes
  question_count, shuffle_questions: bool
  status: draft | active | closed

ExamAttempt
  id, test_id, student_id, started_at, submitted_at
  mcq_score, total_possible

DissertationAnswer
  id, attempt_id, question_id, student_text
  ai_score, ai_feedback, criterion_scores: jsonb
  human_score, human_feedback
  status: pending | ai_scored | human_reviewed
```

### Phase 4 (extends Phase 1)

```
SchoolClass
  id, org_id, created_by
  name: str, academic_year: str
  UniqueConstraint(org_id, name, academic_year)

ClassMember
  id, class_id → SchoolClass, user_id (JWT identity), added_by
  UniqueConstraint(class_id, user_id)

TestAssignment
  id, test_id → ExamTest, class_id → SchoolClass
  released_at: datetime, closes_at: datetime
  quarter: q1 | q2 | q3 | q4
  assigned_by
  CheckConstraint(closes_at > released_at)
  UniqueConstraint(test_id, class_id)

ExamAttempt (extended)
  + validation_status: pending | validated
  + validated_by: UUID | null
  + validated_at: datetime | null

ScoreComplaint
  id, attempt_id → ExamAttempt, question_id → ExamQuestion (nullable)
  filed_by, reason: str (min 20 chars)
  status: pending | approved | rejected
  reviewed_by, review_note, score_override: float | null
  reviewed_at: datetime | null
  UniqueConstraint(attempt_id, question_id) [question-level]
  PartialUniqueIndex(attempt_id) WHERE question_id IS NULL [total-score]

ExamTest (extended — Migration 013)
  + exam_weight: float (default 1.0, range 0–100)
    → % contribution of this exam to course term grade

ExamDispensation  [Migration 013]
  id, org_id (indexed), student_id, test_id → ExamTest CASCADE
  class_id → SchoolClass CASCADE
  reason: text, granted_by, granted_at
  expires_at: timestamptz | null
  UniqueConstraint(test_id, student_id)
  → Exempts a student from an exam; bypasses FR-4.5 access gate

GradeScale  [Migration 013]
  id, org_id (indexed), min_score, max_score
  letter: varchar(4), gpa_points: float, sort_order: int
  → Org-configurable letter grade thresholds; default = A/B/C/D/F

TermGrade  [Migration 013]
  id, org_id (indexed), student_id, course_code: varchar(32)
  class_id → SchoolClass, academic_year, quarter: q1|q2|q3|q4
  weighted_avg: float | null, grade_letter: varchar(4) | null
  finalized_at: timestamptz
  superseded_by → TermGrade | null
  → Snapshot of term grade; re-finalization links old → new via superseded_by
```

### Phase 2 (extends Phase 1)

```
ExamSession (extends ExamAttempt)
  session_token (HMAC-SHA256), phase: center | remote
  proctor_id, violation_count, last_heartbeat_at
  connectivity_tier, status: active | terminated | completed

ProctorSnapshot
  id, session_id, captured_at, minio_key, ai_flags: jsonb
  face_count, status: pending | analyzed

ProctorEvent
  id, session_id, event_type, severity: info | medium | high | critical
  detected_at, acknowledged_by, details: jsonb

ExamViolation
  id, session_id, violation_type, timestamp, evidence_key

ConsentRecord
  id, session_id, student_id, consented_at, ip_address

DisputeCase
  id, session_id, raised_by, description, status, resolved_at
```

---

## API Contract Summary

### Phase 1 Endpoints
```
# Sources
POST   /api/v1/exam/banks/{id}/sources

# Banks
POST   /api/v1/exam/banks
GET    /api/v1/exam/banks
GET    /api/v1/exam/banks/{id}
PATCH  /api/v1/exam/banks/{id}
DELETE /api/v1/exam/banks/{id}

# Generation
POST   /api/v1/exam/banks/{id}/generate
GET    /api/v1/exam/banks/{id}/generation/status
POST   /api/v1/exam/banks/{id}/scenarios/{sid}/regenerate

# Scenarios & Questions
PATCH  /api/v1/exam/scenarios/{id}
DELETE /api/v1/exam/scenarios/{id}
POST   /api/v1/exam/banks/{id}/questions
PATCH  /api/v1/exam/questions/{id}
DELETE /api/v1/exam/questions/{id}
POST   /api/v1/exam/questions/{id}/validate
POST   /api/v1/exam/banks/{id}/validate-all

# Tests & Attempts
POST   /api/v1/exam/tests/{id}/start
POST   /api/v1/exam/attempts/{id}/submit

# Dissertation review
GET    /api/v1/exam/tests/{id}/dissertation-review
PATCH  /api/v1/exam/answers/{id}/human-score
```

### Phase 4 Additional Endpoints
```
# Class management
POST   /api/v1/exam/classes
GET    /api/v1/exam/classes
GET    /api/v1/exam/classes/{id}
PATCH  /api/v1/exam/classes/{id}
DELETE /api/v1/exam/classes/{id}
POST   /api/v1/exam/classes/{id}/members
GET    /api/v1/exam/classes/{id}/members
DELETE /api/v1/exam/classes/{id}/members/{userId}

# Test scheduling
POST   /api/v1/exam/tests/{id}/assignments
GET    /api/v1/exam/tests/{id}/assignments
PATCH  /api/v1/exam/tests/{id}/assignments/{assignmentId}
DELETE /api/v1/exam/tests/{id}/assignments/{assignmentId}

# Bank → tests navigation (enhanced)
GET    /api/v1/exam/banks/{id}/tests

# Student test discovery
GET    /api/v1/exam/student/tests
GET    /api/v1/exam/student/history

# Teacher submission management
GET    /api/v1/exam/tests/{id}/submissions
GET    /api/v1/exam/attempts/{id}/full-review
POST   /api/v1/exam/attempts/{id}/validate
POST   /api/v1/exam/tests/{id}/batch-validate

# Student read-only review
GET    /api/v1/exam/attempts/{id}/review

# Score complaints (student)
POST   /api/v1/exam/attempts/{id}/complaints
GET    /api/v1/exam/attempts/{id}/complaints

# Score complaints (teacher)
GET    /api/v1/exam/tests/{id}/complaints
PATCH  /api/v1/exam/complaints/{id}
```

### Phase 2 Additional Endpoints
```
POST   /api/v1/exam/sessions
POST   /api/v1/exam/sessions/{id}/heartbeat
GET    /api/v1/exam/sessions/{id}/snapshot-url
POST   /api/v1/exam/sessions/{id}/snapshot-recorded
GET    /api/v1/exam/monitor/queue
GET    /api/v1/exam/monitor/{id}
GET    /api/v1/exam/monitor/{id}/snapshots
POST   /api/v1/exam/monitor/{id}/acknowledge
POST   /api/v1/exam/monitor/{id}/terminate
POST   /api/v1/exam/monitor/{id}/flag

WS     /api/v1/exam/ws/{session_id}?token=  (candidate)
WS     /api/v1/exam/monitor/{session_id}     (proctor)
```

---

## Async Task Flow

### Exam Generation
```
POST /generate
  │
  └─▶ Celery: generate_exam_task
        │
        ├─ Load ExamSource.raw_text for all sources
        ├─ Build Claude prompt with tool: save_exam(scenarios, questions)
        ├─ Call claude-sonnet-4-6 (forced tool use)
        ├─ Parse tool result → create ExamScenario + ExamQuestion rows
        └─ bank.status = "review"
```

### Attempt Start — Phase 4 Gate (FR-4.5)
```
POST /tests/{id}/start
  │
  ├─ Guard: test.status == published
  ├─ Guard (if test.assignments non-empty):
  │     ├─ Find assignment where released_at ≤ now ≤ closes_at
  │     │     └─ None found → 403 "Test window not open"
  │     └─ Check ClassMember(class_id=assignment.class_id, user_id=student)
  │           └─ Not found → 403 "Not enrolled in any class for this test"
  └─ Create ExamAttempt (unchanged from Phase 1)
```

### Dissertation Correction
```
POST /attempts/{id}/submit
  │
  └─▶ For each dissertation question:
        Celery: ai_correct_dissertation_task
          │
          ├─ Fetch student_text + model_answer + rubric
          ├─ Call claude-sonnet-4-6 with grading prompt
          ├─ Parse {score, feedback, criterion_scores}
          └─ DissertationAnswer.status = "ai_scored"
```

### Proctoring (Phase 2)
```
Browser: periodic JPEG capture
  │
  └─▶ GET /snapshot-url → presigned PUT URL
        │
        └─▶ PUT file to MinIO
              │
              └─▶ POST /snapshot-recorded
                    │
                    └─▶ Celery: analyze_snapshot_task
                          │
                          ├─ Download frame
                          ├─ Claude Vision → ai_flags
                          ├─ Create ProctorEvent if violation
                          └─ WS fanout to proctor dashboard
```

---

## Auth Flow (Sira JWT Integration)

```
Client Request
  │
  ├─ Authorization: Bearer <sira_jwt>
  │
  └─▶ FastAPI deps.py: get_current_user()
        │
        ├─ jwt.decode(token, SIRA_JWT_SECRET, algorithms=["HS256"])
        ├─ Extract: user_id, org_id, role
        └─ Return CurrentUser(id, org_id, role)
              │
              └─▶ All service calls filter by org_id
```

---

## Deployment

### Local Development
```bash
make up          # docker compose up --build
make migrate     # alembic upgrade head
make test-be     # pytest inside backend container
make lint-be     # ruff check + format
```

### Staging / Production
- Docker images pushed to `ghcr.io/benidrissa/sira-exam-service`
- SSH-based deploy via `.github/workflows/deploy.yml`
- `deploy.yml` triggers: push to `main` or manual `workflow_dispatch`
- Post-deploy: `alembic upgrade head` runs automatically

### CI
- Trigger: push to `main`, PR to `main`
- Backend: ruff check + format, pytest (≥30% coverage) with PostgreSQL 16 + Redis 7
- Frontend: eslint, next build

---

## Cross-Repo Pattern Reference

All pattern lookups should check `~/devprojects/etutor_digital_ph` first:
- FastAPI dep injection → `etutor_digital_ph/backend/app/api/deps.py`
- Celery task structure → `etutor_digital_ph/backend/app/tasks/`
- JWT auth → `etutor_digital_ph/backend/app/core/auth.py`
- Next.js API client → `etutor_digital_ph/frontend/src/lib/api.ts`
