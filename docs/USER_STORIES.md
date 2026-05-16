# User Stories — Sira Exam Service

> All user stories derive from [SRS.md](SRS.md). Each story maps to functional requirements and GitHub issues.
> UAT validation runs against **staging** (see CLAUDE.md for staging URLs).

---

## Phase 1 — Base Exam Platform

---

## US-1: Create Exam Bank and Upload Sources

**As a** Teacher  
**I want to** create an exam bank, upload PDF source documents, and verify they are processed  
**So that** I can use course material as the basis for AI-generated exam questions

### Preconditions
- Authenticated teacher JWT issued by Sira auth
- Staging stack running at configured staging URL
- At least one PDF (≥ 2 pages) available for upload

### Steps
1. `POST /api/v1/exam/banks` with `{title, description, org_id}`
2. Receive 201 + `ExamBankResponse` with `status=draft`
3. `POST /api/v1/exam/banks/{id}/sources` with PDF file multipart upload
4. Receive 201 + `ExamSource` with `status=pending`
5. Poll `GET /api/v1/exam/banks/{id}/sources/{sid}` until `status=done`

### Acceptance Criteria
- [ ] AC1: Bank creation returns 201 with all fields populated
- [ ] AC2: Source upload returns 201 with `status=pending`
- [ ] AC3: Within 30s, source `status=done` and `raw_text` is non-empty
- [ ] AC4: Uploading an unsupported file type returns 422
- [ ] AC5: Bank is isolated to requesting teacher's `org_id` (another org's teacher gets 404)

### Linked FRs: FR-1.0, FR-1.2  
### Linked GitHub Issues: #6, #29

---

## US-2: Generate AI Exam Questions from Sources

**As a** Teacher  
**I want to** trigger AI generation of exam questions based on my uploaded sources and specify the exam structure  
**So that** I get a set of contextually relevant, scenario-based questions to review

### Preconditions
- US-1 completed: bank exists with at least one source in `status=done`

### Steps
1. `POST /api/v1/exam/banks/{id}/generate` with `{test_objective, scenarios_brief: [{title, question_count, types}]}`
2. Receive 202 + `{task_id}`
3. Poll `GET /api/v1/exam/banks/{id}/generation/status` every 5s
4. Wait until `bank.status=review` (max 120s)
5. `GET /api/v1/exam/banks/{id}` to see all scenarios and questions

### Acceptance Criteria
- [ ] AC1: POST /generate returns 202 immediately (not blocking)
- [ ] AC2: Status endpoint shows `pending → processing → review`
- [ ] AC3: Bank has the requested number of scenarios with ≥1 question each
- [ ] AC4: Questions have `stem`, `type`, `points` populated
- [ ] AC5: `bank.status=review` after success

### Linked FRs: FR-1.3, FR-1.4  
### Linked GitHub Issues: #8, #9

---

## US-3: Edit and Publish an Exam Bank

**As a** Teacher  
**I want to** edit generated questions, validate them, and publish the bank  
**So that** students can be assigned to exams derived from the bank

### Preconditions
- US-2 completed: bank in `status=review`

### Steps
1. `PATCH /api/v1/exam/questions/{id}` to edit a question stem or rubric
2. Verify partial update (only patched fields changed)
3. `POST /api/v1/exam/questions/{id}/validate` for each question
4. `POST /api/v1/exam/banks/{id}/validate-all` to bulk-validate
5. Verify `bank.status=published`
6. Try to publish a bank with at least one unvalidated question → expect 422

### Acceptance Criteria
- [ ] AC1: PATCH updates only the supplied fields
- [ ] AC2: Validate-all returns 200 and sets `bank.status=published`
- [ ] AC3: Publishing is blocked when any question `validated=false`
- [ ] AC4: Teacher from different org cannot edit this bank (404)

### Linked FRs: FR-1.5, FR-1.6  
### Linked GitHub Issues: #10, #11

---

## US-4: Student Takes an MCQ Exam

**As a** Student  
**I want to** start an exam session, answer multiple-choice questions, and receive my score instantly  
**So that** I know how I performed immediately after submission

### Preconditions
- US-3 completed: bank `status=published`; an `ExamTest` exists and is `active`
- Authenticated student JWT

### Steps
1. `POST /api/v1/exam/tests/{id}/start` — receive `ExamAttempt` with shuffled questions
2. Answer all MCQ questions (record `{question_id, selected_option}` per question)
3. `POST /api/v1/exam/attempts/{id}/submit` with `mcq_answers` array
4. Receive attempt response with `mcq_score` and `total_possible`

### Acceptance Criteria
- [ ] AC1: Start returns 201 with `question_count` questions
- [ ] AC2: Questions are shuffled when `shuffle_questions=true`
- [ ] AC3: Submit returns `mcq_score` (correct count × points)
- [ ] AC4: Double submission returns 409
- [ ] AC5: Expired test returns 403 on start

### Linked FRs: FR-1.7  
### Linked GitHub Issue: #12

---

## US-5: Student Answers Dissertation Question — AI Grades It

**As a** Student  
**I want to** write a long-form answer and have it automatically graded by AI  
**So that** I get preliminary feedback before the teacher reviews

### Preconditions
- ExamTest includes at least one `dissertation` type question
- Student has started the attempt (US-4 step 1)

### Steps
1. `POST /api/v1/exam/attempts/{id}/submit` with `dissertation_answers: [{question_id, student_text}]`
2. Receive attempt response (dissertation answers `status=pending`)
3. Poll `GET /api/v1/exam/attempts/{id}/answers` every 10s until `status=ai_scored`
4. Verify `ai_score`, `ai_feedback`, `criterion_scores` populated

### Acceptance Criteria
- [ ] AC1: Submit creates `DissertationAnswer` rows with `status=pending`
- [ ] AC2: Within 60s, `status=ai_scored` with non-empty `ai_feedback`
- [ ] AC3: `criterion_scores` matches the question rubric structure
- [ ] AC4: Empty `student_text` returns 422

### Linked FRs: FR-1.7, FR-1.8  
### Linked GitHub Issues: #12, #13

---

## US-6: Teacher Reviews and Overrides Dissertation Grade

**As a** Teacher  
**I want to** see AI-scored dissertation answers and override the grade if needed  
**So that** the final grade reflects my pedagogical judgment

### Preconditions
- US-5 completed: at least one `DissertationAnswer` with `status=ai_scored`

### Steps
1. `GET /api/v1/exam/tests/{id}/dissertation-review` — list all answers needing review
2. Review AI score + criterion breakdown for one answer
3. `PATCH /api/v1/exam/answers/{id}/human-score` with `{human_score: 14, human_feedback: "Good analysis but..."}`
4. Verify `status=human_reviewed`
5. Try the same as a student role → expect 403

### Acceptance Criteria
- [ ] AC1: Review list returns only answers for the teacher's bank
- [ ] AC2: PATCH sets `human_score` and `status=human_reviewed`
- [ ] AC3: Student cannot call PATCH (403)
- [ ] AC4: `human_score > question.points` returns 422

### Linked FRs: FR-1.9  
### Linked GitHub Issue: #14

---

## US-7: Teacher Uses Generation Brief Wizard in Browser

**As a** Teacher  
**I want to** create an exam bank through a guided 4-step wizard in the browser  
**So that** I can configure exam parameters without knowing the API directly

### Preconditions
- Staging frontend accessible in browser
- Authenticated teacher session (Sira SSO cookie)

### Steps
1. Navigate to `/create` — wizard step 1 appears (Exam info)
2. Fill title + description → click Next → bank created via API
3. Upload a PDF → extraction status badge appears (pending → done)
4. Configure 2 scenarios (titles + question counts) → click Next
5. Click "Generate" → polling banner shows progress
6. Wait until banner shows "Ready for review" and Scenarios appear

### Acceptance Criteria
- [ ] AC1: Step 1 submission creates bank via API (visible in network tab)
- [ ] AC2: Upload step shows spinner while `status=pending`, checkmark on `done`
- [ ] AC3: Generation step shows polling banner with status text
- [ ] AC4: On completion, user is navigated to review board
- [ ] AC5: Browser: no JS console errors throughout wizard

### Linked FRs: FR-1.10  
### Linked GitHub Issue: #15

---

## US-8: Teacher Reviews and Edits Question Cards in Browser

**As a** Teacher  
**I want to** edit scenario cards, question stems, and rubrics inline in the browser  
**So that** I can refine AI output before publishing

### Preconditions
- US-7 completed (bank in `review` status)

### Steps
1. On review board, click into a scenario card — inline editing enabled
2. Edit a question stem → autosave fires (PATCH visible in network tab)
3. Open rubric editor for a dissertation question → add a criterion
4. Click "Validate question" → validated badge appears
5. Click "Validate all" → all questions show validated; publish button appears
6. Click "Publish" → bank `status=published`

### Acceptance Criteria
- [ ] AC1: Inline edit triggers PATCH after debounce (≤1s)
- [ ] AC2: Rubric editor allows adding/removing criteria
- [ ] AC3: Validation badge updates without page reload
- [ ] AC4: Publish button disabled if any question unvalidated
- [ ] AC5: Browser: no JS console errors

### Linked FRs: FR-1.11  
### Linked GitHub Issue: #16

---

## US-9: Student Completes Exam in Browser — Timer Auto-Submit

**As a** Student  
**I want to** take an exam in the browser with a timer that auto-submits when time is up  
**So that** the exam is fair and the same duration for all students

### Preconditions
- ExamTest with `time_limit_minutes=1` (for test) and MCQ + 1 dissertation question
- Student authenticated in staging browser

### Steps
1. Navigate to exam player URL → questions load grouped by scenario
2. Answer MCQ questions
3. Type text in dissertation `<textarea>`
4. Let timer expire (1 minute) → auto-submit fires
5. Verify redirect to results page with `mcq_score`

### Acceptance Criteria
- [ ] AC1: Timer visible in header, counts down correctly
- [ ] AC2: Auto-submit on expiry (PATCH visible in network)
- [ ] AC3: After auto-submit: MCQ score shown, dissertation shows "AI grading..."
- [ ] AC4: Cannot modify answers after submission (inputs disabled)
- [ ] AC5: Browser: no JS console errors

### Linked FRs: FR-1.12  
### Linked GitHub Issue: #17

---

## US-10: Teacher Grades Dissertations in Browser

**As a** Teacher  
**I want to** see AI-scored dissertations in the grading page and override scores  
**So that** I can efficiently review and finalize grades

### Preconditions
- US-9 completed: at least one dissertation submitted and `ai_scored`

### Steps
1. Navigate to `/exams/{bankId}/results/` — list of attempts needing review
2. Click an attempt → see student text + AI score + criterion breakdown
3. If answer still `pending`, see "AI grading..." with 30s auto-refresh
4. Enter `human_score` + feedback in the override form → submit
5. Verify answer card shows `human_reviewed` badge

### Acceptance Criteria
- [ ] AC1: Results page lists all attempts with pending/ai_scored/human_reviewed status
- [ ] AC2: 30s TanStack Query refresh while `status=pending`
- [ ] AC3: Override form PATCH updates score immediately in UI
- [ ] AC4: Browser: no JS console errors

### Linked FRs: FR-1.13  
### Linked GitHub Issue: #18

---

## Phase 2 — Proctoring Layer

---

## US-11: Student Completes Pre-Check and Starts Proctored Exam

**As a** Student  
**I want to** pass a system and identity check before starting a remote exam  
**So that** my identity is verified and my device is confirmed as compatible

### Preconditions
- Phase 2 deployed to staging
- ExamTest configured as `phase=remote`
- Browser with camera + fullscreen capability

### Steps
1. Navigate to `/session/pre-check/`
2. Step 1: System check passes (camera access, fullscreen available, resolution ≥ 720p)
3. Step 2: Camera preview shown; reference frame captured
4. Step 3: Photo ID captured and uploaded to MinIO
5. Step 4: Video proctoring consent checkbox → accept
6. Session starts; lockdown shell activates (fullscreen, no right-click)

### Acceptance Criteria
- [ ] AC1: System check fails gracefully if camera denied (show instructions)
- [ ] AC2: Reference frame upload returns 201
- [ ] AC3: Consent creates `ConsentRecord` in DB
- [ ] AC4: Lockdown shell blocks right-click and context menu
- [ ] AC5: Heartbeat `POST /sessions/{id}/heartbeat` fires every 30s

### Linked FRs: FR-2.2, FR-2.7, FR-2.10  
### Linked GitHub Issues: #20, #25, #28

---

## US-12: Proctor Monitors Live Sessions and Flags Violations

**As a** Proctor  
**I want to** see a real-time dashboard of active exam sessions with webcam snapshots and violation alerts  
**So that** I can intervene when suspicious behavior is detected

### Preconditions
- Phase 2 deployed to staging
- At least one active ExamSession with webcam capture enabled
- Proctor authenticated (teacher role)

### Steps
1. Navigate to proctor dashboard
2. See session grid with latest snapshots refreshing every 5s
3. A HIGH violation alert banner appears (AI detected anomaly)
4. Click session → see violation feed timeline
5. Click "Acknowledge" on the alert → banner clears
6. Click "Terminate session" on a suspicious session

### Acceptance Criteria
- [ ] AC1: Dashboard grid updates snapshots every 5s (TanStack Query poll)
- [ ] AC2: Violation badge increments in real time
- [ ] AC3: ProctorAlert banner shows for HIGH/CRITICAL unacknowledged events
- [ ] AC4: Acknowledge updates `acknowledged_by` and clears banner
- [ ] AC5: Terminate sets `session.status=terminated`

### Linked FRs: FR-2.6, FR-2.9  
### Linked GitHub Issues: #24, #27

---

## Phase 3 — Edge AI + Lockdown Hardening

---

## US-13: Student Verifies Identity with Selfie + ID Before Exam

**As a** Student
**I want to** photograph myself holding my government-issued ID next to my face before the exam
**So that** my identity is confirmed and the system can prove the exam taker matches the ID

### Preconditions
- Phase 3 deployed to staging
- ExamTest configured as `phase=remote`
- Browser with camera + fullscreen capability
- Student has a government-issued photo ID available

### Steps
1. Navigate to `/session/pre-check/`
2. Complete system check (step 1) and camera preview (step 2)
3. Arrive at **Identity Verification** step
4. Read overlay instructions: "Hold your ID document next to your face within the frame"
5. Click "Capture photo" → spinner appears
6. Wait ≤15s for AI validation result
7. **On success**: green "Verified ✅" badge appears → "Next" button enabled
8. **On rejection**: red banner with reason (e.g., "ID document not visible") + "Retry" button
9. After 3 consecutive failures → "Verification failed — a proctor will review your session" message; exam blocked

### Acceptance Criteria
- [ ] AC1: Identity verification step appears in pre-check wizard between camera-preview and consent
- [ ] AC2: "Capture" button disabled until live webcam feed is active
- [ ] AC3: AI result shown within 15s of capture
- [ ] AC4: Success → green badge, "Next" enabled, proceed to consent step
- [ ] AC5: Failure → human-readable reason displayed, "Retry" button shown
- [ ] AC6: After 3 failures → session flagged, exam blocked, proctor alerted on dashboard
- [ ] AC7: Exam cannot start until `session.identity_verified=True` (backend enforced)
- [ ] AC8: Browser: no JS console errors throughout flow

### Linked FRs: FR-3.15
### Linked GitHub Issue: #119
