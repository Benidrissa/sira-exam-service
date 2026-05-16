"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { startAttempt, submitAttempt, startProctoringSession, terminateSession, getVLMConfig } from "@/lib/api";
import type { ExamQuestion, StartAttemptResponse, VLMConfigResponse } from "@/types/exam";
import { useLockdownShell } from "@/hooks/useLockdownShell";
import { useWebcamProctor } from "@/hooks/useWebcamProctor";
import { useEdgeProctor } from "@/hooks/useEdgeProctor";
import { useConnectivityProbe } from "@/hooks/useConnectivityProbe";
import { OfflineBanner } from "@/components/OfflineBanner";
import { openOfflineDb } from "@/lib/offlineDb";
import { drain } from "@/lib/offlineSync";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { cn } from "@/lib/utils";
import { Timer } from "lucide-react";

export default function ExamPlayerPage() {
  const { testId, locale } = useParams<{ testId: string; locale?: string }>();
  const effectiveLocale = (locale as string) ?? "fr";
  const router = useRouter();
  const [showConfirm, setShowConfirm] = useState(false);
  const [session, setSession] = useState<StartAttemptResponse | null>(null);
  const [mcqAnswers, setMcqAnswers] = useState<Record<string, number[]>>({});
  const [dissertations, setDissertations] = useState<Record<string, string>>({});
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const startTimeRef = useRef<number>(Date.now());

  // Proctoring state
  const [proctoringSessionId, setProctoringSessionId] = useState<string | null>(null);
  const [proctoringToken, setProctoringToken] = useState<string | null>(null);
  const [isRemoteExam, setIsRemoteExam] = useState(false);
  const [snapshotIntervalMs, setSnapshotIntervalMs] = useState(10_000);
  const [offlineDb, setOfflineDb] = useState<IDBDatabase | null>(null);
  const [vlmConfig, setVlmConfig] = useState<VLMConfigResponse | null>(null);
  // aiTier is written to sessionStorage during pre-check (E3-12); read once on mount
  const aiTier = (
    typeof sessionStorage !== "undefined"
      ? parseInt(sessionStorage.getItem("proctor_ai_tier") ?? "0", 10)
      : 0
  ) as 0 | 1 | 2;

  // Initialize IndexedDB
  useEffect(() => {
    openOfflineDb().then(setOfflineDb).catch(console.error);
  }, []);

  // Fetch VLM config when edge AI is required (aiTier > 0)
  useEffect(() => {
    if (aiTier > 0) {
      getVLMConfig().then(setVlmConfig).catch(console.error);
    }
  // aiTier is a constant derived from sessionStorage — no reactive deps needed
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Restore proctoring session across hard reloads (React state is not persistent)
  useEffect(() => {
    const savedId = sessionStorage.getItem("proctor_session_id");
    const savedToken = sessionStorage.getItem("proctor_session_token");
    if (savedId && savedToken) {
      setProctoringSessionId(savedId);
      setProctoringToken(savedToken);
      setIsRemoteExam(true);
    }
  }, []);

  const handleForceTerminate = useCallback(async () => {
    if (proctoringSessionId) {
      try {
        await terminateSession(proctoringSessionId);
      } catch (e) {
        console.error("Force terminate failed:", e);
      } finally {
        sessionStorage.removeItem("proctor_session_id");
        sessionStorage.removeItem("proctor_session_token");
      }
    }
    router.push(`/${effectiveLocale}/exams/${testId}/results?reason=lockdown_violation`);
  }, [proctoringSessionId, router, testId, effectiveLocale]);

  const handleDrain = useCallback(async () => {
    if (!proctoringSessionId || !proctoringToken || !offlineDb) return;
    await drain(proctoringSessionId, proctoringToken, offlineDb);
  }, [proctoringSessionId, proctoringToken, offlineDb]);

  const { connectivityState, offlineDurationSeconds, sessionExpired } = useConnectivityProbe(
    proctoringSessionId,
    proctoringToken,
    handleDrain,
  );

  // Lockdown shell — enabled only for remote exams
  const { fullscreenActive, fullscreenCountdown, violationCount } = useLockdownShell(
    isRemoteExam,
    proctoringSessionId,
    proctoringToken,
    handleForceTerminate,
  );

  // Webcam proctoring — enabled only for remote exams
  const { videoRef, registerEdgeResult } = useWebcamProctor(
    proctoringSessionId,
    proctoringToken,
    isRemoteExam,
    snapshotIntervalMs,
    connectivityState,
    offlineDb,
    aiTier,
    vlmConfig,
  );

  // Edge AI worker — only active when aiTier > 0 and vlmConfig is loaded
  const MEDIAPIPE_WASM = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.22/wasm";
  useEdgeProctor({
    enabled: isRemoteExam && aiTier > 0 && vlmConfig !== null,
    mediapipeWasmUrl: MEDIAPIPE_WASM,
    taskModelUrl: vlmConfig?.tier1_models[0]?.url ?? "",
    onnxModelUrl: vlmConfig?.tier1_models[1]?.url ?? "",
    modelVersion: vlmConfig?.model_version ?? "",
    onReady: () => console.log("[EdgeProctor] worker ready"),
    onUnsupported: (reason) => console.warn("[EdgeProctor] unsupported:", reason),
    onResult: (result) => registerEdgeResult(result.snapshotId, result),
  });

  useEffect(() => {
    startAttempt(testId)
      .then(async (s) => {
        setSession(s);
        if (s.time_limit_minutes) setSecondsLeft(s.time_limit_minutes * 60);

        setIsRemoteExam(true);
        try {
          const ps = await startProctoringSession(s.attempt_id);
          setProctoringSessionId(ps.session_id);
          setProctoringToken(ps.session_token);
          setSnapshotIntervalMs(ps.snapshot_interval_ms);
          sessionStorage.setItem("proctor_session_id", ps.session_id);
          sessionStorage.setItem("proctor_session_token", ps.session_token);
        } catch (procErr) {
          console.error("Failed to start proctoring session:", procErr);
        }
      })
      .catch((e: unknown) => {
        const httpStatus = (e as { status?: number })?.status;
        if (httpStatus === 409) {
          router.push(`/${effectiveLocale}/exams/${testId}/results`);
        } else {
          setError(String(e));
        }
      })
      .finally(() => setLoading(false));
  }, [testId]);

  // Countdown timer
  useEffect(() => {
    if (secondsLeft === null || secondsLeft <= 0 || submitted) return;
    const id = setInterval(() => setSecondsLeft((s) => (s !== null && s > 0 ? s - 1 : 0)), 1000);
    return () => clearInterval(id);
  }, [secondsLeft, submitted]);

  const handleSubmit = useCallback(async () => {
    if (!session || submitting || submitted) return;
    setSubmitting(true);
    try {
      const elapsed = Math.round((Date.now() - startTimeRef.current) / 1000);
      const result = await submitAttempt(session.attempt_id, {
        mcq_answers: mcqAnswers,
        dissertation_answers: dissertations,
        time_taken_sec: elapsed,
      });

      if (proctoringSessionId) {
        try {
          await terminateSession(proctoringSessionId);
        } catch (e) {
          console.error("Failed to terminate proctoring session:", e);
        } finally {
          sessionStorage.removeItem("proctor_session_id");
          sessionStorage.removeItem("proctor_session_token");
        }
      }

      setSubmitted(true);
      const params = new URLSearchParams({ attemptId: String(result.id) });
      if (result.mcq_score != null) params.set("score", String(result.mcq_score));
      if (result.total_score != null) params.set("total", String(result.total_score));
      if (result.passed != null) params.set("passed", String(result.passed));
      router.push(`/${effectiveLocale}/exams/${testId}/results?${params.toString()}`);
    } catch (e) {
      setError(String(e));
      setSubmitting(false);
    }
  }, [session, mcqAnswers, dissertations, submitting, submitted, router, testId, proctoringSessionId, effectiveLocale]);

  // Auto-submit when timer hits 0
  useEffect(() => {
    if (secondsLeft === 0) handleSubmit();
  }, [secondsLeft, handleSubmit]);

  function selectMCQ(questionId: string, idx: number) {
    if (submitted) return;
    setMcqAnswers((prev) => ({ ...prev, [questionId]: [idx] }));
  }

  if (loading) return (
    <div className="flex items-center justify-center p-8 gap-2 text-sm text-muted-foreground">
      <LoadingSpinner className="h-4 w-4" />
      Starting exam…
    </div>
  );
  if (error) return <p className="p-8 text-sm text-destructive">{error}</p>;
  if (!session) return null;

  const fmt = (s: number) =>
    `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

  const timerColor =
    secondsLeft !== null
      ? secondsLeft < 60
        ? "text-red-600 animate-pulse"
        : secondsLeft < 300
          ? "text-amber-500"
          : "text-foreground"
      : "";

  const answeredCount =
    Object.keys(mcqAnswers).length +
    Object.keys(dissertations).filter((k) => dissertations[k]).length;
  const totalCount = session.questions.length;
  const progressValue = totalCount > 0 ? (answeredCount / totalCount) * 100 : 0;

  return (
    <main className="max-w-3xl mx-auto pb-24">
      <OfflineBanner state={connectivityState} offlineDurationSeconds={offlineDurationSeconds} />

      {/* Sticky header */}
      <div className="sticky top-0 z-10 bg-background/95 backdrop-blur shadow-sm border-b">
        <div className="flex items-center justify-between px-6 py-3 gap-4">
          {/* Left: title + answered count */}
          <div className="flex flex-col min-w-0">
            <span className="text-base font-semibold truncate">Exam</span>
            <span className="text-xs text-muted-foreground">
              {answeredCount}/{totalCount} answered
            </span>
          </div>

          {/* Center: timer */}
          {secondsLeft !== null && (
            <div className={cn("flex items-center gap-1.5 font-mono text-2xl font-bold tabular-nums", timerColor)}>
              <Timer className="h-5 w-5 shrink-0" />
              {fmt(secondsLeft)}
            </div>
          )}

          {/* Right: submit button */}
          <Button
            disabled={submitting || submitted || connectivityState === "DRAINING"}
            onClick={() => setShowConfirm(true)}
          >
            {submitting ? (
              <>
                <LoadingSpinner className="h-4 w-4" />
                Submitting…
              </>
            ) : submitted ? "Submitted" : "Submit Exam"}
          </Button>
        </div>

        {/* Progress bar */}
        <Progress value={progressValue} className="rounded-none h-1" />
      </div>

      <div className="px-6 pt-6 space-y-4">
        {/* Submit confirmation modal */}
        {showConfirm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
            <Card className="w-full max-w-sm shadow-xl">
              <CardHeader>
                <CardTitle>Submit Exam?</CardTitle>
                <p className="text-sm text-muted-foreground">
                  You have answered {answeredCount} of {totalCount} question{totalCount !== 1 ? "s" : ""}.
                  This cannot be undone.
                </p>
              </CardHeader>
              <CardFooter className="gap-3 pt-4">
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={() => setShowConfirm(false)}
                >
                  Keep Working
                </Button>
                <Button
                  className="flex-1"
                  onClick={() => { setShowConfirm(false); handleSubmit(); }}
                >
                  Submit Now
                </Button>
              </CardFooter>
            </Card>
          </div>
        )}

        {/* Fullscreen gate — shown only for remote exams when fullscreen is lost */}
        {isRemoteExam && !fullscreenActive ? (
          <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4 text-center px-6">
            <p className="text-xl font-semibold text-destructive">Fullscreen Required</p>
            <p className="text-sm text-muted-foreground max-w-xs">
              Your exam requires fullscreen mode. Press{" "}
              <kbd className="px-1 py-0.5 text-xs bg-muted rounded">F11</kbd>{" "}
              or click below to continue.
            </p>
            {fullscreenCountdown > 0 && (
              <p className="text-sm font-mono text-amber-600 font-semibold">
                Session terminates in {fullscreenCountdown}s if not restored
              </p>
            )}
            <button
              className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:bg-primary/90"
              onClick={() => void document.documentElement.requestFullscreen()}
            >
              Return to Fullscreen
            </button>
            {violationCount > 0 && (
              <p className="text-xs text-muted-foreground">{violationCount} violation(s) recorded</p>
            )}
          </div>
        ) : (
          <>
            {session.questions.length === 0 && (
              <p className="text-center py-12 text-muted-foreground text-sm">
                No questions available for this exam.
              </p>
            )}

            {session.questions.map((q, i) => (
              <QuestionBlock
                key={q.id}
                index={i + 1}
                question={q}
                mcqAnswer={mcqAnswers[q.id] ?? []}
                dissertationText={dissertations[q.id] ?? ""}
                submitted={submitted}
                onMCQSelect={(idx) => selectMCQ(q.id, idx)}
                onDissertationChange={(text) =>
                  setDissertations((d) => ({ ...d, [q.id]: text }))
                }
              />
            ))}
          </>
        )}
      </div>

      {/* Session expired modal */}
      {sessionExpired && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-background rounded-lg p-6 max-w-sm text-center space-y-3">
            <p className="font-semibold text-destructive">Session Expired</p>
            <p className="text-sm text-muted-foreground">
              Your exam session expired during the network outage. Please contact your instructor.
            </p>
          </div>
        </div>
      )}

      {/* Webcam proctoring badge */}
      {isRemoteExam && proctoringSessionId && (
        <div className="fixed bottom-4 right-4 z-50 rounded-xl border-2 border-emerald-500 overflow-hidden shadow-lg">
          <video
            ref={videoRef}
            autoPlay
            muted
            playsInline
            className="w-32 h-24 object-cover"
            aria-label="Webcam proctoring feed"
          />
          <span className="absolute top-1.5 right-1.5 rounded-sm bg-red-600 px-1 py-0.5 text-[10px] font-bold text-white leading-none">
            REC
          </span>
        </div>
      )}
    </main>
  );
}

function QuestionBlock({
  index,
  question,
  mcqAnswer,
  dissertationText,
  submitted,
  onMCQSelect,
  onDissertationChange,
}: {
  index: number;
  question: ExamQuestion;
  mcqAnswer: number[];
  dissertationText: string;
  submitted: boolean;
  onMCQSelect: (idx: number) => void;
  onDissertationChange: (text: string) => void;
}) {
  return (
    <Card className="mb-4">
      <CardHeader>
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant={question.question_type === "mcq" ? "info" : "purple"}>
            {question.question_type.toUpperCase()}
          </Badge>
          <Badge variant="secondary" className="font-mono">
            Q{index}
          </Badge>
        </div>
        {question.title && (
          <p className="text-sm font-medium text-foreground">{question.title}</p>
        )}
        <CardTitle className="text-sm font-normal text-muted-foreground leading-relaxed">
          {question.description}
        </CardTitle>
      </CardHeader>

      <CardContent>
        {question.question_type === "mcq" && question.options && (
          <div className="space-y-2">
            {question.options.map((opt, idx) => {
              const selected = mcqAnswer.includes(idx);
              return (
                <div
                  key={idx}
                  onClick={() => !submitted && onMCQSelect(idx)}
                  className={cn(
                    "flex items-center gap-3 rounded-lg border p-3 cursor-pointer transition-colors",
                    selected
                      ? "border-primary bg-primary/5"
                      : "border-border hover:bg-muted",
                    submitted && "cursor-default",
                  )}
                >
                  <input
                    type="radio"
                    name={`q-${question.id}`}
                    disabled={submitted}
                    checked={selected}
                    onChange={() => onMCQSelect(idx)}
                    className="accent-primary shrink-0"
                  />
                  <Badge variant="outline" className="font-mono shrink-0">
                    {opt.label}
                  </Badge>
                  <span className="text-sm">{opt.text}</span>
                </div>
              );
            })}
          </div>
        )}

        {question.question_type === "dissertation" && (
          <Textarea
            rows={8}
            disabled={submitted}
            placeholder="Write your answer here…"
            value={dissertationText}
            onChange={(e) => onDissertationChange(e.target.value)}
          />
        )}
      </CardContent>
    </Card>
  );
}
