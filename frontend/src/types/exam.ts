export type BankStatus = "draft" | "generating" | "review" | "published" | "archived";
export type ExtractionStatus = "pending" | "extracting" | "done" | "failed";
export type QuestionType = "mcq" | "dissertation";
export type DissertationStatus = "pending" | "ai_scored" | "human_reviewed";
export type TestStatus = "draft" | "published" | "archived";

export interface ExamBank {
  id: string;
  org_id: string;
  created_by: string;
  title_fr: string;
  title_en: string | null;
  subject: string | null;
  language: string;
  passing_score: number;
  status: BankStatus;
  generation_task_id: string | null;
  generation_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExamSource {
  id: string;
  bank_id: string;
  filename: string;
  storage_key: string;
  raw_text: string | null;
  char_count: number | null;
  extraction_status: ExtractionStatus;
  error_message: string | null;
  created_at: string;
}

export interface ExamScenario {
  id: string;
  bank_id: string;
  title: string;
  objective: string | null;
  context_text: string | null;
  context_image_storage_key: string | null;
  order_index: number;
  created_at: string;
  updated_at: string;
}

export interface MCQOption {
  label: string;
  text: string;
}

export interface RubricCriterion {
  criterion: string;
  max_points: number;
  description: string;
}

export interface ExamQuestion {
  id: string;
  bank_id: string;
  scenario_id: string | null;
  question_type: QuestionType;
  title: string | null;
  description: string;
  image_storage_key: string | null;
  image_url: string | null;
  options: MCQOption[] | null;
  correct_answer_indices: number[] | null;
  explanation: string | null;
  model_answer: string | null;
  rubric: RubricCriterion[] | null;
  difficulty: string;
  category: string | null;
  order_index: number;
  ai_generated: boolean;
  validated: boolean;
  created_at: string;
  updated_at: string;
}

export interface GenerationStatusResponse {
  bank_id: string;
  task_id: string | null;
  status: BankStatus;
  task_state: string | null;
  progress_pct: number | null;
  scenario_count: number | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExamAttempt {
  id: string;
  test_id: string;
  user_id: string;
  question_ids: string[];
  mcq_answers: Record<string, number[]> | null;
  mcq_score: number | null;
  total_score: number | null;
  passed: boolean | null;
  time_taken_sec: number | null;
  attempted_at: string;
}

export interface DissertationAnswer {
  id: string;
  attempt_id: string;
  question_id: string;
  answer_text: string;
  ai_score: number | null;
  ai_feedback: string | null;
  criterion_scores: Record<string, number> | null;
  ai_scored_at: string | null;
  human_score: number | null;
  human_feedback: string | null;
  human_scored_by: string | null;
  human_scored_at: string | null;
  status: DissertationStatus;
  created_at: string;
}

export interface BulkValidationResponse {
  bank_id: string;
  validated_count: number;
  bank_status: BankStatus;
}

export interface ScenarioBrief {
  title: string;
  objective: string;
  question_count: number;
}

export interface StartAttemptResponse {
  attempt_id: string;
  test_id: string;
  user_id: string;
  bank_id: string;
  question_ids: string[];
  time_limit_minutes: number | null;
  questions: ExamQuestion[];
}

// ---------------------------------------------------------------------------
// Proctoring types
// ---------------------------------------------------------------------------

export interface ProctoringSession {
  session_id: string;
  session_token: string;
  expires_in: number;
  snapshot_interval_ms: number;
}

/** Forensic record of a connectivity interruption — E3-8 */
export interface NetworkGap {
  id: string;
  session_id: string;
  disconnected_at: string;
  reconnected_at: string | null;
  duration_seconds: number | null;
  missed_heartbeat_count: number;
  auto_expired: boolean;
}

export interface SessionSummary {
  id: string;
  user_id: string;
  started_at: string;
  status: "active" | "disconnected" | "terminated" | "expired" | "completed";
  unacked_alert_count: number;
  latest_snapshot_url: string | null;
  consecutive_missed_heartbeats: number;
  /** Timestamp when session went offline (status === "disconnected") — E3-8 */
  disconnected_at?: string | null;
  /** Sum of all gap durations in seconds — E3-8 */
  total_offline_duration_s?: number | null;
  /** Count of network interruption events — E3-8 */
  offline_event_count?: number;
}

export interface ProctorAlert {
  id: string;
  severity: "info" | "low" | "medium" | "high" | "critical";
  message: string;
  acknowledged: boolean;
  created_at: string;
}

export interface SessionEvent {
  id: string;
  event_type: string;
  severity: string;
  occurred_at: string;
  payload: unknown;
}

export interface SessionSnapshot {
  id: string;
  storage_key: string;
  taken_at: string;
  violation_detected: boolean | null;
  download_url: string | null;
  /** E3-14: Edge AI verdict for this frame ("clean" | "flagged" | null) */
  edge_verdict?: string | null;
  /** E3-14: Confidence score from edge model (0–1) */
  edge_confidence?: number | null;
  /** E3-14: True when frame was captured during an offline gap */
  is_offline_frame?: boolean;
  /** E3-14: Whether SHA-256 integrity check passed on server */
  integrity_check_passed?: boolean | null;
}

export interface SessionDetail extends SessionSummary {
  events: SessionEvent[];
  alerts: ProctorAlert[];
  snapshots: SessionSnapshot[];
  /** Chronological list of offline intervals — E3-8 */
  network_gaps: NetworkGap[];
}

export interface VLMConfigResponse {
  model_version: string;
  cdn_base: string;
  tier1_models: { name: string; url: string; sha256: string }[];
  tier2_model: { name: string; url: string; sha256: string } | null;
  mandatory_sample_rate: number;
}
