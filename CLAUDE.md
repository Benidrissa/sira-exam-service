# CLAUDE.md — Sira Exam Service

## Cross-Repo Reference (ALWAYS CHECK FIRST)
Before implementing any feature, search `~/devprojects/etutor_digital_ph` for existing solutions:
- Auth/JWT middleware patterns
- FastAPI route and dependency patterns
- Celery task definitions
- Next.js page and component patterns
- Alembic migration patterns
- Pytest fixtures and test utilities

Never reinvent what `etutor_digital_ph` already solved.

---

## Single Source of Truth
All requirements live in `docs/SRS.md`. Every PR must reference its SRS section (e.g., `Implements FR-1.3`).
If implementation must diverge from SRS: update `docs/SRS.md` first (separate PR), then implement.

User stories are in `docs/USER_STORIES.md`. Architecture in `docs/ARCHITECTURE.md`.

---

## Git Workflow (MANDATORY — NO EXCEPTIONS)
- Branch model: `feature/<issue-id>-<slug>` → `dev` → `main`
- **NEVER** commit directly to `main` or `dev`
- Every issue gets its own feature branch cut from `dev`
- PRs: `feature/*` → `dev` (squash merge); `dev` → `main` (merge commit, after full phase)
- Branch naming: `feature/E1-1-exambank-crud`, `feature/E2-3-minio-upload`

---

## Worktrees (parallel coding)
```bash
# Start a new issue in a fresh worktree
git worktree add ../sira-ws-<issue-id> dev
cd ../sira-ws-<issue-id>
git checkout -b feature/<issue-id>-<slug>

# Clean up after PR merge
git worktree remove ../sira-ws-<issue-id>
```
- Worktree base dir: `/home/bitraore/devprojects/` (siblings to main checkout)
- Each agent works in its own worktree — never share between agents

---

## Agent Orchestration (MANDATORY — 3 agents before any implementation)
Always spawn these 3 agents in parallel before writing code:
1. **Architecture agent** — domain model, API contract, edge cases, SRS alignment
2. **Implementation agent** — concrete code plan, reuse from etutor_digital_ph, file paths
3. **Test/QA agent** — test strategy, UAT scenario mapping, coverage targets

Synthesize all 3 reports before writing a single line of code.
Maximize parallel tool calls at every subsequent step.

---

## Autonomy Rules
- All `Bash(*)`, `Edit(*)`, `Write(*)`, `Read(*)` are pre-approved — **never pause for permission**
- Never idle — always have the next issue queued before the current PR merges
- All code written locally in VS Code; do NOT assign issues to GitHub Copilot or external agents

---

## UAT & Browser Validation
- Each feature must pass its UAT scenario (issues labeled `uat` and `docs/USER_STORIES.md`)
- **Always validate on staging — not localhost** (staging auto-deploys on every `main` push)
- Staging URLs:
  - Frontend: https://sira-exam.elearning.portfolio2.kimbetien.com
  - Backend API docs: https://sira-exam-api.elearning.portfolio2.kimbetien.com/docs
- Staging server: `deploy@167.86.115.58` (shared infra with etutor, Traefik `proxy` network)
- Include in PR description: staging URL visited, each AC checked, pass/fail
- E2E: `npx playwright test` — target staging base URL

---

## Code Standards
| Layer | Linter | Formatter | Test runner | Coverage gate |
|-------|--------|-----------|-------------|---------------|
| Backend | `ruff check` | `ruff format` | `pytest` | ≥30% |
| Frontend | `eslint` | `prettier` | `vitest` | — |

- Python: ruff line-length 100, mypy strict mode
- TypeScript: strict mode, no `any`
- Commit style: `feat(E1-1): ...`, `fix(E2-3): ...`, `test(E1-7): ...`
- Run `make lint-be && make test-be` before every backend PR
- Run `make lint-fe` before every frontend PR

---

## Issue Workflow (repeat until STOP)
```
1. Pick lowest-numbered open issue on GitHub
2. Create worktree from dev:
   git worktree add ../sira-ws-<id> dev
   cd ../sira-ws-<id> && git checkout -b feature/<id>-<slug>
3. Spawn 3 brainstorm agents (parallel)
4. Check etutor_digital_ph for prior art
5. Implement (maximize parallel agents/tools)
6. make lint-be test-be  OR  make lint-fe
7. Open PR: feature/<id> → dev  (body: "Implements FR-x.y, closes #<n>")
8. Move to next issue immediately
```

---

## PR Merge Pipeline (MANDATORY — every feature PR)

Run these 5 steps in order before picking the next issue:

```
1. AGENT CODE REVIEW
   Spawn a review agent to read all changed files and check:
   - SRS FR alignment (does implementation match the linked FR?)
   - ruff + mypy compliance (no lint errors)
   - Test coverage ≥30% (new code has tests)
   - org_id filtering on all DB queries (no cross-tenant data leaks)
   - No hardcoded secrets or credentials
   - Celery tasks are idempotent (safe to retry)
   Output: APPROVE or REQUEST_CHANGES with file:line specifics.
   Fix all REQUEST_CHANGES before proceeding.

2. MERGE feature → dev  (squash merge)
   gh pr merge <number> --squash --delete-branch

3. MERGE dev → main  (phase boundary only — not per-issue)
   Only when an entire phase milestone is complete.
   gh pr create --base main --head dev --title "chore: Phase X complete"
   gh pr merge <number> --merge

4. CURL STAGING HEALTH CHECK  (after main merges → deploy auto-triggers)
   until curl -sf https://sira-exam-api.elearning.portfolio2.kimbetien.com/health; do
     echo "waiting for deploy..."; sleep 15; done
   curl -s https://sira-exam-api.elearning.portfolio2.kimbetien.com/health | jq .

5. BROWSER UAT VALIDATION
   Open https://sira-exam.elearning.portfolio2.kimbetien.com
   Run the relevant UAT scenario from docs/USER_STORIES.md
   Check each AC: pass ✅ / fail ❌
   Post result as comment on the GitHub issue, then close it.
```

---

## Stack Quick Reference
- Backend API: http://localhost:8001 | Docs: http://localhost:8001/docs
- Frontend: http://localhost:3001
- PostgreSQL: shared sira_db, schema: exam_svc
- Redis: redis://redis:6379/0 (keys namespaced `exam:*`)
- MinIO: http://minio:9000, bucket: exam-evidence
- Celery worker: see `backend/app/tasks/`
