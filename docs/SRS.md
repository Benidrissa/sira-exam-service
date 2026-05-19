# Software Requirements Specification
## Sira Exam Service — v1.0

> **This document is the single source of truth.** All GitHub issues, PRs, and implementation decisions must reference the FR number defined here. If code must diverge from an FR, update this document first (separate PR), then implement.

---

## 1. Introduction

### 1.1 Purpose
Define the functional and non-functional requirements for the Sira Exam Service, a standalone microservice that provides AI-generated proctored exams for university accreditation within the Sira learning platform.

### 1.2 Scope
The service covers:
- Exam bank creation and AI-powered question generation (Phase 1)
- Student exam sessions with MCQ and dissertation support (Phase 1)
- Remote proctoring with webcam capture, violation detection, and evidence storage (Phase 2)
- Edge AI lockdown hardening + identity verification (Phase 3)
- Class roster management, test scheduling, score validation, and student score complaints (Phase 4)

Out of scope: LMS core, user management, billing (handled by the parent Sira platform).

### 1.3 Definitions
| Term | Definition |
|------|-----------|
| ExamBank | Top-level container grouping one or more exam scenarios |
| ExamScenario | A contextual block within a bank (e.g., a case study) |
| ExamQuestion | Individual question (MCQ or dissertation) under a scenario |
| ExamTest | Published test derived from a bank, assigned to students |
| ExamAttempt | A student's session answering a specific ExamTest |
| DissertationAnswer | Open-text student response requiring AI + human grading |
| ExamSession | Extended attempt with proctoring metadata (Phase 2) |
| ProctorSnapshot | Periodic webcam frame stored in MinIO evidence bucket |
| ProctorEvent | Violation or anomaly event recorded during a session |
| SchoolClass | A named cohort scoped to `(org_id, name, academic_year)`; tests are assigned to classes (Phase 4) |
| ClassMember | Enrollment record linking a student `user_id` to a `SchoolClass` (Phase 4) |
| TestAssignment | Scheduled delivery of an `ExamTest` to a `SchoolClass` with `released_at`, `closes_at`, and `quarter` (Phase 4) |
| ScoreComplaint | Student-initiated dispute on a question score or total attempt score (Phase 4) |

### 1.4 References
- [ARCHITECTURE.md](ARCHITECTURE.md) — technical design
- [USER_STORIES.md](USER_STORIES.md) — UAT scenarios
- GitHub repository: https://github.com/Benidrissa/sira-exam-service
- Cross-reference: `~/devprojects/etutor_digital_ph` (prior art patterns)

---

## 2. Overall Description

### 2.1 Product Perspective
The Exam Service is a bounded microservice within the Sira ecosystem. It shares:
- PostgreSQL instance (isolated schema `exam_svc`)
- Redis instance (keys namespaced `exam:*`)
- MinIO instance (bucket `exam-evidence`)
- JWT authentication issued by the Sira auth service

### 2.2 User Classes
| Class | Description | Access Level |
|-------|------------|--------------|
| Teacher | Creates banks, reviews AI output, grades dissertations | Full CRUD on own banks; read-only on students |
| Student | Takes exams, views own results | Create/read own attempts |
| Admin | Manages org-level banks, overrides | All teacher permissions + org management |
| Proctor | Monitors live sessions in Phase 2 | Read-only session monitoring + acknowledge/flag |

### 2.3 Operating Environment
- Backend: Python 3.12, FastAPI, PostgreSQL 16, Redis 7, Celery
- Frontend: Next.js 16, React 19, TypeScript strict
- Infrastructure: Docker Compose (local), GHCR + SSH deploy (production)
- AI: Anthropic Claude (claude-sonnet-4-6) for generation and grading

---

## 3. Functional Requirements — Phase 1 (Base Exam Platform)

### FR-1.0: ExamSource — PDF Upload & Extraction
**GitHub Issue:** #6  
**Priority:** P0 (dependency for generation)

- FR-1.0.1: `POST /api/v1/exam/banks/{id}/sources` accepts PDF/Word files; stores in MinIO; creates `ExamSource(status=pending)` row.
- FR-1.0.2: `extract_exam_source_task` Celery task: PyMuPDF extraction → `raw_text`, `char_count`, `status=done`.
- FR-1.0.3: Failed extraction sets `status=error` with `error_message`.
- FR-1.0.4: Source text is used as context for exam generation (FR-1.3).

**Acceptance Criteria:**
- AC1: Upload returns 201 + ExamSource row with `status=pending`
- AC2: After task completion, source `status=done` and `raw_text` populated
- AC3: Unsupported file type returns 422
- AC4: CI passes (ruff + pytest ≥30%)

---

### FR-1.1: Domain Models & Pydantic Schemas
**GitHub Issue:** #7  
**Priority:** P0 (foundation for all other FRs)

- FR-1.1.1: SQLAlchemy models: `ExamBank`, `ExamScenario`, `ExamQuestion`, `ExamTest` in `exam_svc` schema.
- FR-1.1.2: Pydantic V2 request/response schemas for all models.
- FR-1.1.3: Alembic migration 001 creates all Phase 1 tables.
- FR-1.1.4: Models include `created_by`, `org_id`, `status`, `created_at`, `updated_at`.

**Acceptance Criteria:**
- AC1: Migration applies cleanly against PostgreSQL 16
- AC2: All schemas pass `mypy --strict`
- AC3: No direct FK to Sira tables (integration via JWT claims only)

---

### FR-1.2: ExamBank CRUD
**GitHub Issue:** #29  
**Priority:** P1

- FR-1.2.1: `POST /api/v1/exam/banks` creates a bank; returns 201 + `ExamBankResponse`.
- FR-1.2.2: `GET /api/v1/exam/banks` returns only banks for requesting teacher's `org_id`.
- FR-1.2.3: `GET /api/v1/exam/banks/{id}` returns 404 for wrong org.
- FR-1.2.4: `PATCH /api/v1/exam/banks/{id}` partial update (only provided fields).
- FR-1.2.5: `DELETE /api/v1/exam/banks/{id}` soft-delete → `status=archived`, returns 204.

**Acceptance Criteria:** per issue #29 body.

---

### FR-1.3: AI Generation — Brief Endpoint + Task
**GitHub Issue:** #8  
**Priority:** P1 (depends on FR-1.0, FR-1.1)

- FR-1.3.1: `POST /api/v1/exam/banks/{id}/generate` — body: `{test_objective, scenarios_brief[]}`.
- FR-1.3.2: `generate_exam_task` Celery task: loads ExamSource texts → calls `claude-sonnet-4-6` with `save_exam()` forced tool use → writes scenarios + questions → sets `bank.status=review`.
- FR-1.3.3: Failed generation sets `bank.status=draft` + `generation_error`.

**Acceptance Criteria:**
- AC1: POST enqueues task and returns 202 + `task_id`
- AC2: After task, bank has N scenarios with M questions each
- AC3: `bank.status=review` on success, `draft` on failure

---

### FR-1.4: Generation Status Polling & Per-Scenario Regeneration
**GitHub Issue:** #9  
**Priority:** P1 (depends on FR-1.3)

- FR-1.4.1: `GET /api/v1/exam/banks/{id}/generation/status` — polls Celery task state.
- FR-1.4.2: Timeout / permanent failure → `bank.status=draft` + `generation_error`.
- FR-1.4.3: `POST /api/v1/exam/banks/{id}/scenarios/{sid}/regenerate` — re-fires Claude for a single scenario.

---

### FR-1.5: Bank/Scenario/Question Full CRUD
**GitHub Issue:** #10  
**Priority:** P1

- FR-1.5.1: GET/PATCH/DELETE on `/exam/banks/{id}`, `/exam/scenarios/{id}`, `/exam/questions/{id}`.
- FR-1.5.2: All mutations verify `created_by == current_user OR role=admin`.
- FR-1.5.3: Bulk question creation: `POST /exam/banks/{id}/questions`.

---

### FR-1.6: Question Validation & Publish Gate
**GitHub Issue:** #11  
**Priority:** P1

- FR-1.6.1: `POST /exam/questions/{id}/validate` → `validated=True`.
- FR-1.6.2: `POST /exam/banks/{id}/validate-all` → bulk validate → `bank.status=published`.
- FR-1.6.3: Publish is blocked until all questions are validated.

---

### FR-1.7: ExamAttempt — Start & Submit
**GitHub Issue:** #12  
**Priority:** P1 (depends on FR-1.6)

- FR-1.7.1: `POST /exam/tests/{id}/start` — draws `question_count` questions (shuffled if enabled) → creates `ExamAttempt`.
- FR-1.7.2: `POST /exam/attempts/{id}/submit` — scores MCQ answers server-side; creates `DissertationAnswer` rows (`status=pending`) for open questions.
- FR-1.7.3: MCQ score calculated immediately and stored on attempt.

---

### FR-1.8: Dissertation Answer & AI Correction Task
**GitHub Issue:** #13  
**Priority:** P1 (depends on FR-1.7)

- FR-1.8.1: `DissertationAnswer` model: `student_text`, `ai_score`, `ai_feedback`, `criterion_scores`, `human_score`, `human_feedback`, `status`.
- FR-1.8.2: `ai_correct_dissertation_task` Celery task: fetches answer + `question.model_answer` + `question.rubric` → calls `claude-sonnet-4-6` with grading prompt → stores result → `status=ai_scored`.

---

### FR-1.9: Dissertation Review Endpoints
**GitHub Issue:** #14  
**Priority:** P1 (depends on FR-1.8)

- FR-1.9.1: `GET /exam/tests/{id}/dissertation-review` — all answers needing human review (teacher only).
- FR-1.9.2: `PATCH /exam/answers/{id}/human-score` — `{human_score, human_feedback}` → `status=human_reviewed`.

---

### FR-1.10: Frontend — Generation Brief Wizard
**GitHub Issue:** #15  
**Priority:** P2 (depends on FR-1.2, FR-1.3, FR-1.4)

- FR-1.10.1: 4-step shadcn wizard: (1) Exam info, (2) Source upload + extraction status, (3) Scenarios config, (4) Generate button + polling banner.
- FR-1.10.2: Creates bank on step 1; adds sources/scenarios incrementally.
- FR-1.10.3: Generation polling banner shows progress until `bank.status=review`.

---

### FR-1.11: Frontend — Review & Edit Board
**GitHub Issue:** #16  
**Priority:** P2 (depends on FR-1.10)

- FR-1.11.1: `exam-review-board.tsx`, `scenario-card.tsx`, `question-card.tsx` (inline edit, type-aware MCQ/dissertation), `rubric-editor.tsx`, `generation-status-banner.tsx`.
- FR-1.11.2: Inline editing saves via PATCH with debounce.

---

### FR-1.12: Frontend — Student Exam Player
**GitHub Issue:** #17  
**Priority:** P2 (depends on FR-1.7)

- FR-1.12.1: Scenario context block above grouped questions.
- FR-1.12.2: MCQ: radio/checkbox. Dissertation: `<textarea>`.
- FR-1.12.3: Timer if `time_limit_minutes` set; auto-submit on expiry.
- FR-1.12.4: Submits both `mcq_answers` and `dissertation_answers`.

---

### FR-1.13: Frontend — Dissertation Grading Page
**GitHub Issue:** #18  
**Priority:** P2 (depends on FR-1.9)

- FR-1.13.1: Lists all attempts needing review for a given bank.
- FR-1.13.2: Per-answer: student text, AI score + criterion breakdown (TanStack Query poll 30s while pending).
- FR-1.13.3: Editable human score + feedback. PATCH `/exam/answers/{id}/human-score`.

---

## 4. Functional Requirements — Phase 2 (Proctoring Layer)

### FR-2.1: Alembic Migration 002 — Proctoring Tables
**GitHub Issue:** #19  
**Priority:** P0 for Phase 2

Tables: `exam_sessions`, `proctor_snapshots`, `proctor_events`, `exam_violations`, `exam_accommodations`, `consent_records`, `dispute_cases` — all in `exam_svc` schema.

---

### FR-2.2: ExamSession Model + Token Issuance + Heartbeat
**GitHub Issue:** #20

- FR-2.2.1: `ExamSession` extends `ExamAttempt` with SHA-256 hash of cryptographically random token (secrets.token_urlsafe(32)) `session_token`, `phase` (center/remote), `proctor_id`, `violation_count`, `last_heartbeat_at`, `connectivity_tier`, `status`.
- FR-2.2.2: `POST /exam/sessions` — issues token.
- FR-2.2.3: `POST /exam/sessions/{id}/heartbeat`.

---

### FR-2.3: WebSocket + Redis Pub/Sub Signaling
**GitHub Issue:** #21

- FR-2.3.1: `WS /api/v1/exam/ws/{session_id}?token=` (candidate connection).
- FR-2.3.2: `WS /api/v1/exam/monitor/{session_id}` (proctor, requires teacher role).
- FR-2.3.3: Redis channel `proctor:session:{id}` fanout. Redis HASH `exam:session:{id}:state`.

---

### FR-2.4: MinIO Evidence Bucket + Presigned URLs
**GitHub Issue:** #22

- FR-2.4.1: Private ACL bucket. `GET /exam/sessions/{id}/snapshot-url` → presigned PUT URL.
- FR-2.4.2: `POST /exam/sessions/{id}/snapshot-recorded` → creates `ProctorSnapshot` row, dispatches `analyze_snapshot_task`.

---

### FR-2.5: Celery Proctoring Tasks
**GitHub Issue:** #23

- FR-2.5.1: `analyze_snapshot_task`: download frame → Claude Vision → parse `ai_flags` → `ProctorEvent` on violation.
- FR-2.5.2: `check_heartbeat_task` (Celery beat 30s): detect missed heartbeats → flag session.
- FR-2.5.3: `finalize_session_task`: SHA-256 evidence digest.

---

### FR-2.6: Proctor Monitor API
**GitHub Issue:** #24

Endpoints: GET queue, GET session, GET snapshots (presigned URLs), POST acknowledge/terminate/flag/override. All require teacher role.

---

### FR-2.7: Frontend — Exam Lockdown Shell
**GitHub Issue:** #25

- FR-2.7.1: `requestFullscreen` enforcement + change listener.
- FR-2.7.2: Right-click/copy/devtools keydown intercept, CSS `user-select:none`.
- FR-2.7.3: Window resize second-monitor heuristic (Phase 2).
- FR-2.7.4: Exam Zustand store (no persist).

---

### FR-2.8: Frontend — Webcam Capture + Violation Transport
**GitHub Issue:** #26

- FR-2.8.1: `getUserMedia` (video+audio), periodic JPEG capture → presigned PUT → snapshot-recorded.
- FR-2.8.2: `FaceDetector` API heuristic.
- FR-2.8.3: Violation buffer → `sendBeacon/fetch keepalive` every 10s + on `beforeunload`.

---

### FR-2.9: Frontend — Proctor Dashboard
**GitHub Issue:** #27

- FR-2.9.1: TanStack Query 5s poll: active sessions grid with latest snapshot + violation count badge + Terminate/Flag buttons.
- FR-2.9.2: Violation feed timeline.
- FR-2.9.3: `ProctorAlert` banner for HIGH/CRITICAL unacknowledged events.

---

### FR-2.10: Frontend — Pre-Check Wizard
**GitHub Issue:** #28

4-step wizard: (1) system check (`getUserMedia`, `fullscreenEnabled`, resolution), (2) camera preview + reference frame, (3) photo ID capture + upload, (4) video proctoring consent checkbox.

---

## 5. Functional Requirements — Phase 3 (Edge AI + Lockdown Hardening)

### FR-3.15: Pre-Exam Selfie + ID Identity Verification
**GitHub Issue:** #119
**Priority:** P0 for phase3-lockdown

- FR-3.15.1: Before a remote exam session becomes `active`, the student must complete an identity-binding step: hold a government-issued photo ID adjacent to their face within the webcam frame and capture a JPEG.
- FR-3.15.2: `POST /exam/sessions/{id}/identity-photo` — accepts `multipart/form-data` JPEG; stores to MinIO key `exam-evidence/{org_id}/{session_id}/identity_{timestamp}.jpg`; creates `IdentityVerificationRecord(status=pending)`.
- FR-3.15.3: `validate_identity_photo_task` Celery task — downloads image → Claude Vision (`claude-sonnet-4-6`) with structured prompt → checks (a) human face visible, (b) ID document visible adjacent to face → sets `ai_status=verified|rejected`, `ai_confidence`, `ai_face_detected`, `ai_id_detected`, `ai_rejection_reason`.
- FR-3.15.4: If `ai_status=rejected`: student sees reason ("Face not detected" / "ID document not visible" / "ID too far from face") and may retry (max 3 attempts). After 3 failures, session is flagged (`ProctorEvent(type=identity_verification_failed)`) for proctor review and exam is blocked.
- FR-3.15.5: `ExamSession.identity_verified` boolean field (Alembic migration); exam start endpoint returns 403 until `identity_verified=True`.
- FR-3.15.6: Frontend pre-check wizard inserts this as a new step between camera-preview and consent: positioning guide overlay, live webcam preview, "Capture" button, loading spinner during AI check, result badge (✅ Verified / ❌ Retry).

**Acceptance Criteria:**
- AC1: `POST /exam/sessions/{id}/identity-photo` returns 201 + `IdentityVerificationRecord` with `status=pending`
- AC2: Within 15s, Celery task updates record to `verified` or `rejected` with `ai_rejection_reason`
- AC3: Rejected result shown in UI with reason string and "Retry" button (up to 3 attempts)
- AC4: Exam start blocked (403) until `session.identity_verified=True`
- AC5: MinIO key follows pattern `exam-evidence/{org_id}/{session_id}/identity_{ts}.jpg`
- AC6: After 3 consecutive rejections, `ProctorEvent(identity_verification_failed)` created and proctor dashboard shows alert
- AC7: CI passes (ruff + mypy strict + pytest ≥30%)

---

## 6. Functional Requirements — Phase 4 (Class Scheduling, Score Validation & Complaints)

### FR-4.1: Bank-to-Test Navigation
**Priority:** P1

- FR-4.1.1: `GET /api/v1/exam/banks/{id}/tests` returns all `ExamTest` rows for the bank, scoped to caller's `org_id`.
- FR-4.1.2: Response includes `assignment_count` (number of `TestAssignment` rows) and `attempt_count` (submitted attempts) per test.
- FR-4.1.3: Archiving a bank does not cascade-delete tests that have submitted attempts; service returns 409 when attempts exist.

**Acceptance Criteria:**
- AC1: GET returns 200 with all tests for the bank
- AC2: Different-org teacher receives 404
- AC3: DELETE bank with submitted attempts returns 409

---

### FR-4.2: SchoolClass CRUD
**Priority:** P1

- FR-4.2.1: `POST /api/v1/exam/classes` — creates a `SchoolClass(org_id, name, academic_year, created_by)`; 409 if `(org_id, name, academic_year)` already exists.
- FR-4.2.2: `GET /api/v1/exam/classes` — returns all classes for caller's org; optional `?academic_year=` filter.
- FR-4.2.3: `GET /api/v1/exam/classes/{id}` — returns class with member list; 404 for wrong org.
- FR-4.2.4: `PATCH /api/v1/exam/classes/{id}` — partial update of `name` or `academic_year`.
- FR-4.2.5: `DELETE /api/v1/exam/classes/{id}` — 409 if class has enrolled members; otherwise hard-delete.

**Acceptance Criteria:**
- AC1: POST returns 201 with all fields populated
- AC2: Duplicate `(org_id, name, academic_year)` returns 409
- AC3: DELETE with enrolled members returns 409
- AC4: Wrong-org teacher receives 404

---

### FR-4.3: ClassMember Enrollment
**Priority:** P1

- FR-4.3.1: `POST /api/v1/exam/classes/{id}/members` — body: `{user_id: UUID}`; creates `ClassMember`; 409 on duplicate `(class_id, user_id)`.
- FR-4.3.2: `GET /api/v1/exam/classes/{id}/members` — returns all enrolled members for the class.
- FR-4.3.3: `DELETE /api/v1/exam/classes/{id}/members/{user_id}` — removes enrollment; 204 on success.
- FR-4.3.4: `user_id` is the cross-service JWT identity; no lookup to Sira user table.

**Acceptance Criteria:**
- AC1: Enroll returns 201 with ClassMember row
- AC2: Duplicate enrollment returns 409
- AC3: DELETE returns 204; member no longer appears in list

---

### FR-4.4: TestAssignment Scheduling
**Priority:** P1

- FR-4.4.1: `POST /api/v1/exam/tests/{id}/assignments` — body: `{class_id, released_at, closes_at, quarter}`; creates `TestAssignment`; 422 if `closes_at ≤ released_at`; 409 if same `(test_id, class_id)` already assigned; 422 if test not `status=published`.
- FR-4.4.2: `GET /api/v1/exam/tests/{id}/assignments` — returns all assignments for the test.
- FR-4.4.3: `PATCH /api/v1/exam/tests/{id}/assignments/{assignment_id}` — update `released_at`, `closes_at`, or `quarter`; 409 if narrowing `closes_at` to past while open (unsubmitted) attempts exist.
- FR-4.4.4: `DELETE /api/v1/exam/tests/{id}/assignments/{assignment_id}` — 409 if any attempts exist for this test; 204 otherwise.
- FR-4.4.5: `quarter` values: `q1`, `q2`, `q3`, `q4`.

**Acceptance Criteria:**
- AC1: POST returns 201 with TestAssignment row
- AC2: `closes_at ≤ released_at` returns 422
- AC3: Assigning a draft test returns 422
- AC4: Duplicate `(test_id, class_id)` returns 409

---

### FR-4.5: Class + Window Gate on Attempt Start
**Priority:** P0 (guards all student exam access)

- FR-4.5.1: `POST /exam/tests/{id}/start` — if the test has `TestAssignment` rows, enforce:
  - At least one assignment has `released_at ≤ now ≤ closes_at` (window open).
  - The requesting student's `user_id` is enrolled in the `class_id` of a valid open assignment.
- FR-4.5.2: If no open window: 403 `"Test window not open"`.
- FR-4.5.3: If window open but student not enrolled: 403 `"Not enrolled in any class for this test"`.
- FR-4.5.4: Tests with **no assignments** are accessible to any authenticated student (backward compatibility with Phases 1–3).
- FR-4.5.5: An in-progress attempt is not terminated when `closes_at` passes — the attempt timer governs completion.

**Acceptance Criteria:**
- AC1: Enrolled student within window → 201 (attempt created)
- AC2: Unenrolled student → 403
- AC3: Enrolled student, window not yet open → 403
- AC4: Enrolled student, window closed → 403
- AC5: Test with no assignments → 201 for any student (backward compat)

---

### FR-4.6: Student Test Discovery
**Priority:** P1

- FR-4.6.1: `GET /api/v1/exam/student/tests` — returns tests available to the authenticated student: finds all `ClassMember` rows for the student, then all `TestAssignment` rows where `now` is within `[released_at, closes_at]`, then the corresponding `ExamTest` rows.
- FR-4.6.2: Response includes `has_attempted: bool` and `attempt_id: UUID | null` per test.
- FR-4.6.3: Response includes `quarter`, `released_at`, `closes_at`, `class_name`, `academic_year` from the matching assignment.

**Acceptance Criteria:**
- AC1: Returns only tests in open windows for the student's enrolled classes
- AC2: `has_attempted=true` if student has a submitted attempt for that test

---

### FR-4.7: Teacher Submission List
**Priority:** P1

- FR-4.7.1: `GET /api/v1/exam/tests/{id}/submissions` — returns all submitted `ExamAttempt` rows for the test (teacher only).
- FR-4.7.2: Each row includes: `attempt_id`, `user_id`, `attempted_at`, `total_score`, `passed`, and per-status counts for dissertation answers (`pending_count`, `ai_scored_count`, `human_reviewed_count`).
- FR-4.7.3: Test must belong to caller's org; 404 otherwise.

**Acceptance Criteria:**
- AC1: Returns all submitted attempts with correct per-status counts
- AC2: Student cannot call this endpoint (403)
- AC3: Wrong-org teacher receives 404

---

### FR-4.8: Individual Attempt Full Review (Teacher)
**Priority:** P1

- FR-4.8.1: `GET /api/v1/exam/attempts/{id}/full-review` — returns the attempt + all question/answer pairs side-by-side (teacher view, always includes correct answers).
- FR-4.8.2: MCQ answers derived from `attempt.mcq_answers` JSONB; dissertation answers from `DissertationAnswer` rows.
- FR-4.8.3: Test must belong to caller's org.

**Acceptance Criteria:**
- AC1: Returns all questions with submitted answers and correct answers
- AC2: Wrong-org teacher receives 404

---

### FR-4.9: Attempt Score Validation
**Priority:** P1

- FR-4.9.1: `POST /api/v1/exam/attempts/{id}/validate` — marks the attempt's scores as teacher-confirmed.
- FR-4.9.2: Guard: all `DissertationAnswer` rows for the attempt must be `status=human_reviewed`; if not, returns 422 with list of pending `answer_id` values.
- FR-4.9.3: Idempotent: validating an already-validated attempt returns 200 (not 409).
- FR-4.9.4: After validation, scores may only be changed via the complaint approval workflow (FR-4.16).

**Acceptance Criteria:**
- AC1: All dissertations human_reviewed → 200, attempt marked validated
- AC2: Any dissertation pending/ai_scored → 422 with list of unreviewed answer IDs
- AC3: Re-validating → 200 (idempotent)

---

### FR-4.10: Batch Score Validation
**Priority:** P1

- FR-4.10.1: `POST /api/v1/exam/tests/{id}/batch-validate` — body: `{attempt_ids: [UUID], override_score?: float}`.
- FR-4.10.2: If `override_score` is null: validates each attempt using current scores (same guard as FR-4.9.2 per attempt).
- FR-4.10.3: If `override_score` is set (0.0–100.0): applies that uniform `total_score` to all listed attempts, recomputes `passed`, marks validated. Individual `DissertationAnswer` rows are not modified.
- FR-4.10.4: Max 100 `attempt_ids` per request.
- FR-4.10.5: All `attempt_ids` must belong to the given `test_id` (org guard applies).
- FR-4.10.6: Partial success: attempts that fail validation are returned in an `errors` list; successes are committed.

**Acceptance Criteria:**
- AC1: Batch of 5 attempts validated → 200 with `validated_count=5`
- AC2: `override_score` set → total_score updated on all, `passed` recomputed
- AC3: `attempt_ids` > 100 → 422
- AC4: Attempt from different test → reported in `errors`, not committed

---

### FR-4.11: Teacher Grading Dashboard (Frontend)
**Priority:** P2

- FR-4.11.1: Page `/exams/[testId]/submissions` — table of all student attempts with columns: student, date, MCQ score, dissertation status counts, total score, validation status.
- FR-4.11.2: Row click → navigate to individual review page.
- FR-4.11.3: Multi-row checkbox → "Batch validate" button opens `BatchGradeDrawer`.
- FR-4.11.4: Teacher can freely switch between individual and batch modes.

---

### FR-4.12: Student Attempt History
**Priority:** P1

- FR-4.12.1: `GET /api/v1/exam/student/history` — returns all submitted `ExamAttempt` rows for the authenticated student, across all tests.
- FR-4.12.2: Each row includes: `attempt_id`, `test_id`, `test_title`, `attempted_at`, `total_score`, `passed`, `validation_status`.
- FR-4.12.3: Scoped to the student's `user_id`; no cross-student access.

**Acceptance Criteria:**
- AC1: Returns all submitted attempts for the student
- AC2: Different student cannot access another's history (403 on attempt-level review)

---

### FR-4.13: Student Read-Only Review
**Priority:** P1

- FR-4.13.1: `GET /api/v1/exam/attempts/{id}/review` — returns the student's own attempt in read-only mode.
- FR-4.13.2: Guard: `attempt.user_id` must equal requesting `user_id`; 403 otherwise.
- FR-4.13.3: Correct answers (`correct_answer_indices`, `explanation`, `model_answer`) are revealed only when **either**: `test.show_feedback=True` OR `test.closes_at < now` (test window has closed). Otherwise these fields are `null` in the response.
- FR-4.13.4: Student's submitted answers are always visible in the response (no gate).
- FR-4.13.5: Response includes `feedback_available: bool` to allow the frontend to render an appropriate banner.

**Acceptance Criteria:**
- AC1: Student sees own submitted answers always
- AC2: Correct answers revealed when `show_feedback=True` or test window closed
- AC3: Correct answers are null (not empty list) when review is locked
- AC4: Different student → 403
- AC5: `feedback_available` flag correctly set in response

---

### FR-4.14: Student History + Review (Frontend)
**Priority:** P2

- FR-4.14.1: Page `/students/me/attempts` — list of past attempts (test title, date, score, passed badge).
- FR-4.14.2: Page `/attempts/[attemptId]/review` — read-only review. Banner shown when `feedback_available=false`: "Results available after [closes_at]".
- FR-4.14.3: "Dispute score" button per question (and one for overall) visible when `feedback_available=true`.

---

### FR-4.15: Score Complaint Filing
**Priority:** P1

- FR-4.15.1: `POST /api/v1/exam/attempts/{id}/complaints` — body: `{question_id?: UUID, reason: str (≥20 chars)}`.
- FR-4.15.2: Guard: `attempt.user_id == requesting user_id`; 403 otherwise.
- FR-4.15.3: Guard: `attempt` must be submitted (not in-progress).
- FR-4.15.4: One complaint per `(attempt_id, question_id)` pair; 409 on duplicate.
- FR-4.15.5: One total-score complaint per attempt (`question_id=null`); 409 on duplicate.
- FR-4.15.6: `GET /api/v1/exam/attempts/{id}/complaints` — student sees their own complaints for the attempt.

**Acceptance Criteria:**
- AC1: POST returns 201 with `status=pending`
- AC2: Duplicate `(attempt_id, question_id)` → 409
- AC3: `reason` < 20 chars → 422
- AC4: Wrong student → 403

---

### FR-4.16: Complaint Review
**Priority:** P1

- FR-4.16.1: `GET /api/v1/exam/tests/{id}/complaints` — teacher sees all complaints for all attempts of the test.
- FR-4.16.2: `PATCH /api/v1/exam/complaints/{id}` — body: `{status: "approved"|"rejected", review_note: str, score_override?: float}`.
- FR-4.16.3: `review_note` is required when `status=rejected`; 422 if omitted.
- FR-4.16.4: If `approved` and `score_override` provided on a question-level complaint: updates `DissertationAnswer.human_score`, recomputes `ExamAttempt.total_score` and `passed`.
- FR-4.16.5: If `approved` and `score_override` provided on a total-score complaint: updates `ExamAttempt.total_score` directly, recomputes `passed`.
- FR-4.16.6: Guard: complaint must be `status=pending`; 409 if already resolved.
- FR-4.16.7: Test must belong to caller's org.

**Acceptance Criteria:**
- AC1: Approve → 200, `status=approved`
- AC2: Reject without `review_note` → 422
- AC3: Reject with `review_note` → 200, `status=rejected`
- AC4: Approve with `score_override` on question complaint → DissertationAnswer updated, attempt total recomputed
- AC5: Already-resolved complaint → 409

---

### FR-4.17: Score Complaint (Frontend)
**Priority:** P2

- FR-4.17.1: On `/attempts/[attemptId]/review`, a "Dispute score" button per question opens `ScoreComplaintModal` (reason text input, submit).
- FR-4.17.2: Existing complaint shown as a status badge (pending / approved / rejected) instead of the button.
- FR-4.17.3: On `/exams/[testId]/complaints`, teacher sees a table of all complaints with student info, status badge, and "Resolve" action (inline form with approved/rejected + note + optional score override).

---

## 6. Non-Functional Requirements

### 5.1 Performance
- NFR-1: API p95 response time < 200ms for CRUD endpoints (excluding AI generation)
- NFR-2: AI generation task completes within 120s for a 5-scenario bank
- NFR-3: Webcam capture interval ≤ 30s per snapshot

### 5.2 Security
- NFR-4: All endpoints validate Sira JWT (`SIRA_JWT_SECRET`); no unauthenticated access
- NFR-5: Teachers can only access banks/attempts within their `org_id`
- NFR-6: Evidence stored with private ACL; access only via presigned URLs (TTL ≤ 15min)
- NFR-7: Session tokens use HMAC-SHA256 with `EXAM_WATERMARK_SECRET`

### 5.3 Availability & Reliability
- NFR-8: Celery tasks retry 3× with exponential backoff on transient failures
- NFR-9: Failed generation must not leave DB in inconsistent state (idempotent)
- NFR-10: Evidence retained for `EXAM_EVIDENCE_RETENTION_DAYS` (default 2555 days)

### 5.4 Maintainability
- NFR-11: Backend ruff lint passes, mypy strict passes
- NFR-12: Test coverage ≥ 30% (CI gate)
- NFR-13: All migrations reversible (downgrade scripts required)

---

## 7. System Constraints

- CON-1: Share PostgreSQL instance with Sira; use isolated schema `exam_svc`
- CON-2: Share Redis instance; namespace all keys with `exam:`
- CON-3: Share MinIO instance; use dedicated bucket `exam-evidence`
- CON-4: Authentication is delegated to Sira; exam service validates JWT only
- CON-5: No external dependencies on Sira code — integration via JWT claims and HTTP only

---

## 8. Acceptance Criteria Summary

| FR | GitHub Issue | UAT Scenario | Phase |
|----|-------------|--------------|-------|
| FR-1.0 | #6 | US-1 (source upload step) | 1 |
| FR-1.1 | #7 | — (foundation) | 1 |
| FR-1.2 | #29 | US-1 | 1 |
| FR-1.3 | #8 | US-1 | 1 |
| FR-1.4 | #9 | US-2 | 1 |
| FR-1.5 | #10 | US-2 | 1 |
| FR-1.6 | #11 | US-1 | 1 |
| FR-1.7 | #12 | US-3 | 1 |
| FR-1.8 | #13 | US-4 | 1 |
| FR-1.9 | #14 | US-4 | 1 |
| FR-1.10 | #15 | US-5 | 1 |
| FR-1.11 | #16 | US-6 | 1 |
| FR-1.12 | #17 | US-7 | 1 |
| FR-1.13 | #18 | US-8 | 1 |
| FR-2.1 | #19 | — (foundation) | 2 |
| FR-2.2 | #20 | US-9 | 2 |
| FR-2.3 | #21 | US-9 | 2 |
| FR-2.4 | #22 | US-10 | 2 |
| FR-2.5 | #23 | US-10 | 2 |
| FR-2.6 | #24 | US-11 | 2 |
| FR-2.7 | #25 | US-9 | 2 |
| FR-2.8 | #26 | US-10 | 2 |
| FR-2.9 | #27 | US-11 | 2 |
| FR-2.10 | #28 | US-9 (pre-check) | 2 |
| FR-3.15 | #119 | US-13 | 3 |
| FR-4.1 | — | US-14 | 4 |
| FR-4.2 | — | US-15 | 4 |
| FR-4.3 | — | US-15 | 4 |
| FR-4.4 | — | US-16 | 4 |
| FR-4.5 | — | US-15, US-16 | 4 |
| FR-4.6 | — | US-16 | 4 |
| FR-4.7 | — | US-17 | 4 |
| FR-4.8 | — | US-17 | 4 |
| FR-4.9 | — | US-17 | 4 |
| FR-4.10 | — | US-17 | 4 |
| FR-4.11 | — | US-17 | 4 |
| FR-4.12 | — | US-18 | 4 |
| FR-4.13 | — | US-18 | 4 |
| FR-4.14 | — | US-18 | 4 |
| FR-4.15 | — | US-19 | 4 |
| FR-4.16 | — | US-19 | 4 |
| FR-4.17 | — | US-19 | 4 |
