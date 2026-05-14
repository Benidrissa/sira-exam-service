import type {
  BulkValidationResponse,
  DissertationAnswer,
  ExamAttempt,
  ExamBank,
  ExamQuestion,
  ExamScenario,
  ExamSource,
  GenerationStatusResponse,
  ProctoringSession,
  ScenarioBrief,
  SessionDetail,
  SessionSummary,
} from "@/types/exam";

const API_BASE =
  process.env.NEXT_PUBLIC_EXAM_API_URL || "http://localhost:8001/api/v1";

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
    credentials: "include",
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(detail);
  }

  return res.json() as Promise<T>;
}

// Remove Content-Type for multipart uploads
async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    body: form,
    credentials: "include",
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// ExamBank
// ---------------------------------------------------------------------------
export const createExamBank = (data: {
  title_fr: string;
  subject?: string;
  language?: string;
  passing_score?: number;
}) => apiFetch<ExamBank>("/exam/banks", { method: "POST", body: JSON.stringify(data) });

export const getExamBank = (bankId: string) =>
  apiFetch<ExamBank>(`/exam/banks/${bankId}`);

export const listExamBanks = () => apiFetch<ExamBank[]>("/exam/banks");

// ---------------------------------------------------------------------------
// ExamSource
// ---------------------------------------------------------------------------
export const uploadExamSource = (bankId: string, file: File) => {
  const form = new FormData();
  form.append("file", file);
  return apiUpload<ExamSource>(`/exam/banks/${bankId}/sources`, form);
};

export const listExamSources = (bankId: string) =>
  apiFetch<ExamSource[]>(`/exam/banks/${bankId}/sources`);

export const getExamSource = (bankId: string, sourceId: string) =>
  apiFetch<ExamSource>(`/exam/banks/${bankId}/sources/${sourceId}`);

// ---------------------------------------------------------------------------
// Generation
// ---------------------------------------------------------------------------
export const triggerGeneration = (
  bankId: string,
  data: { test_objective: string; scenarios_brief: ScenarioBrief[] },
) =>
  apiFetch<GenerationStatusResponse>(`/exam/banks/${bankId}/generate`, {
    method: "POST",
    body: JSON.stringify(data),
  });

export const getGenerationStatus = (bankId: string) =>
  apiFetch<GenerationStatusResponse>(`/exam/banks/${bankId}/generation/status`);

// ---------------------------------------------------------------------------
// ExamScenario
// ---------------------------------------------------------------------------
export const listScenarios = (bankId: string) =>
  apiFetch<ExamScenario[]>(`/exam/banks/${bankId}/scenarios`);

export const patchScenario = (bankId: string, scenarioId: string, data: Partial<ExamScenario>) =>
  apiFetch<ExamScenario>(`/exam/banks/${bankId}/scenarios/${scenarioId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });

// ---------------------------------------------------------------------------
// ExamQuestion
// ---------------------------------------------------------------------------
export const listQuestions = (bankId: string) =>
  apiFetch<ExamQuestion[]>(`/exam/banks/${bankId}/questions`);

export const patchQuestion = (questionId: string, bankId: string, data: Partial<ExamQuestion>) =>
  apiFetch<ExamQuestion>(`/exam/questions/${questionId}?bank_id=${bankId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });

export const validateQuestion = (questionId: string, bankId: string) =>
  apiFetch<ExamQuestion>(`/exam/questions/${questionId}/validate?bank_id=${bankId}`, {
    method: "POST",
  });

export const validateAll = (bankId: string) =>
  apiFetch<BulkValidationResponse>(`/exam/banks/${bankId}/validate-all`, {
    method: "POST",
  });

// ---------------------------------------------------------------------------
// ExamAttempt (student)
// ---------------------------------------------------------------------------
export const startAttempt = (testId: string) =>
  apiFetch<import("@/types/exam").StartAttemptResponse>(`/exam/tests/${testId}/start`, { method: "POST" });

export const submitAttempt = (
  attemptId: string,
  data: {
    mcq_answers: Record<string, number[]>;
    dissertation_answers: Record<string, string>;
    time_taken_sec?: number;
  },
) =>
  apiFetch<ExamAttempt>(`/exam/attempts/${attemptId}/submit`, {
    method: "POST",
    body: JSON.stringify(data),
  });

// ---------------------------------------------------------------------------
// Dissertation review (teacher)
// ---------------------------------------------------------------------------
export const getDissertationReview = (testId: string) =>
  apiFetch<DissertationAnswer[]>(`/exam/tests/${testId}/dissertation-review`);

export const patchHumanScore = (
  answerId: string,
  data: { human_score: number; human_feedback: string },
) =>
  apiFetch<DissertationAnswer>(`/exam/answers/${answerId}/human-score`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });

// ---------------------------------------------------------------------------
// ExamQuestion (single, for exam player)
// ---------------------------------------------------------------------------
export const getQuestions = async (
  bankId: string,
  questionIds: string[],
): Promise<ExamQuestion[]> => {
  const all = await listQuestions(bankId);
  const idSet = new Set(questionIds);
  return all.filter((q) => idSet.has(q.id));
};

// ---------------------------------------------------------------------------
// Proctoring — student-facing
// ---------------------------------------------------------------------------

export async function startProctoringSession(
  attemptId: string,
): Promise<{ session_id: string; session_token: string }> {
  return apiFetch<ProctoringSession>("/proctor/sessions/start", {
    method: "POST",
    body: JSON.stringify({ attempt_id: attemptId }),
  });
}

export async function sendHeartbeat(
  sessionId: string,
  token: string,
): Promise<void> {
  await apiFetch<unknown>(`/proctor/sessions/${sessionId}/heartbeat`, {
    method: "POST",
    headers: { "X-Session-Token": token },
  });
}

export async function giveConsent(sessionId: string): Promise<void> {
  await apiFetch<unknown>(`/proctor/sessions/${sessionId}/consent`, {
    method: "POST",
    body: JSON.stringify({ consent_given: true }),
  });
}

export async function getSnapshotUploadUrl(
  sessionId: string,
  snapshotId: string,
): Promise<{ upload_url: string; storage_key: string }> {
  return apiFetch<{ upload_url: string; storage_key: string }>(
    `/proctor/sessions/${sessionId}/snapshot-upload-url?snapshot_id=${snapshotId}`,
  );
}

export async function recordSnapshot(
  sessionId: string,
  snapshotId: string,
  storageKey: string,
): Promise<void> {
  await apiFetch<unknown>(`/proctor/sessions/${sessionId}/snapshot-recorded`, {
    method: "POST",
    body: JSON.stringify({ snapshot_id: snapshotId, storage_key: storageKey }),
  });
}

export async function getReferenceFrameUploadUrl(
  sessionId: string,
): Promise<{ upload_url: string }> {
  return apiFetch<{ upload_url: string }>(
    `/proctor/sessions/${sessionId}/reference-frame-upload-url`,
  );
}

export async function recordReferenceFrame(
  sessionId: string,
  storageKey: string,
): Promise<void> {
  await apiFetch<unknown>(`/proctor/sessions/${sessionId}/reference-frame-recorded`, {
    method: "POST",
    body: JSON.stringify({ storage_key: storageKey }),
  });
}

export async function terminateSession(sessionId: string): Promise<void> {
  await apiFetch<unknown>(`/proctor/sessions/${sessionId}/terminate`, {
    method: "POST",
    body: JSON.stringify({ reason: "student_submitted" }),
  });
}

// ---------------------------------------------------------------------------
// Proctoring — monitor (teacher-facing)
// ---------------------------------------------------------------------------

export async function listActiveSessions(): Promise<SessionSummary[]> {
  return apiFetch<SessionSummary[]>("/proctor/monitor/sessions?status=active");
}

export async function getSessionDetail(sessionId: string): Promise<SessionDetail> {
  return apiFetch<SessionDetail>(`/proctor/monitor/sessions/${sessionId}`);
}

export async function acknowledgeAlert(alertId: string): Promise<void> {
  await apiFetch<unknown>(`/proctor/monitor/alerts/${alertId}/acknowledge`, {
    method: "PATCH",
    body: JSON.stringify({ acknowledged_by: "proctor" }),
  });
}

export async function terminateSessionAsProctor(
  sessionId: string,
  reason: string,
): Promise<void> {
  await apiFetch<unknown>(`/proctor/monitor/sessions/${sessionId}/terminate`, {
    method: "PATCH",
    body: JSON.stringify({ reason }),
  });
}
