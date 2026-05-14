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

- FR-2.2.1: `ExamSession` extends `ExamAttempt` with HMAC `session_token`, `phase` (center/remote), `proctor_id`, `violation_count`, `last_heartbeat_at`, `connectivity_tier`, `status`.
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

## 5. Non-Functional Requirements

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

## 6. System Constraints

- CON-1: Share PostgreSQL instance with Sira; use isolated schema `exam_svc`
- CON-2: Share Redis instance; namespace all keys with `exam:`
- CON-3: Share MinIO instance; use dedicated bucket `exam-evidence`
- CON-4: Authentication is delegated to Sira; exam service validates JWT only
- CON-5: No external dependencies on Sira code — integration via JWT claims and HTTP only

---

## 6. Acceptance Criteria Summary

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
