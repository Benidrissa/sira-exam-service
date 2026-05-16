"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { startAttempt, submitAttempt, startProctoringSession, terminateSession } from "@/lib/api";
import type { ExamQuestion, StartAttemptResponse } from "@/types/exam";
import { useLockdownShell } from "@/hooks/useLockdownShell";
import { useWebcamProctor } from "@/hooks/useWebcamProctor";

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

  // Lockdown shell — enabled only for remote exams
  useLockdownShell(isRemoteExam);

  // Webcam proctoring — enabled only for remote exams
  const { videoRef } = useWebcamProctor(
    proctoringSessionId,
    proctoringToken,
    isRemoteExam,
  );

  useEffect(() => {
    startAttempt(testId)
      .then(async (s) => {
        setSession(s);
        if (s.time_limit_minutes) setSecondsLeft(s.time_limit_minutes * 60);

        // Start proctoring session (treat all attempts as remote for now;
        // a real implementation would check exam.mode from the test payload)
        setIsRemoteExam(true);
        try {
          const ps = await startProctoringSession(s.attempt_id);
          setProctoringSessionId(ps.session_id);
          setProctoringToken(ps.session_token);
          sessionStorage.setItem("proctor_session_id", ps.session_id);
          sessionStorage.setItem("proctor_session_token", ps.session_token);
        } catch (procErr) {
          console.error("Failed to start proctoring session:", procErr);
          // Do not block the exam — log and continue
        }
      })
      .catch((e) => setError(String(e)))
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
      await submitAttempt(session.attempt_id, {
        mcq_answers: mcqAnswers,
        dissertation_answers: dissertations,
        time_taken_sec: elapsed,
      });

      // Terminate proctoring session after exam submission
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
      router.push(`/${effectiveLocale}/exams/${testId}/results`);
    } catch (e) {
      setError(String(e));
      setSubmitting(false);
    }
  }, [session, mcqAnswers, dissertations, submitting, submitted, router, testId, proctoringSessionId]);

  // Auto-submit when timer hits 0
  useEffect(() => {
    if (secondsLeft === 0) handleSubmit();
  }, [secondsLeft, handleSubmit]);

  function selectMCQ(questionId: string, idx: number) {
    if (submitted) return;
    setMcqAnswers((prev) => ({ ...prev, [questionId]: [idx] }));
  }

  if (loading) return <p className="p-8 text-sm text-gray-500">Starting exam…</p>;
  if (error) return <p className="p-8 text-sm text-red-600">{error}</p>;
  if (!session) return null;

  const fmt = (s: number) =>
    `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  const timerColor =
    secondsLeft !== null
      ? secondsLeft < 60
        ? "text-red-600 animate-pulse"
        : secondsLeft < 300
          ? "text-orange-500"
          : "text-gray-700"
      : "";

  return (
    <main className="max-w-3xl mx-auto p-6 pb-24">
      {/* Sticky header */}
      <div className="sticky top-0 z-10 bg-white border-b shadow-sm">
        <div className="flex items-center justify-between py-3 gap-3">
          <div className="flex flex-col">
            <h1 className="text-sm font-semibold text-gray-900">Exam</h1>
            <span className="text-xs text-gray-400">
              {Object.keys(mcqAnswers).length + Object.keys(dissertations).filter(k => dissertations[k]).length}
              /{session.questions.length} answered
            </span>
          </div>
          {secondsLeft !== null && (
            <span className={`font-mono text-2xl font-bold tabular-nums ${timerColor}`}>
              {fmt(secondsLeft)}
            </span>
          )}
          <button
            disabled={submitting || submitted}
            onClick={() => setShowConfirm(true)}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50 transition-colors">
            {submitting ? "Submitting…" : submitted ? "Submitted ✓" : "Submit"}
          </button>
        </div>
        {/* Progress bar */}
        {session.questions.length > 0 && (
          <div className="h-0.5 bg-gray-100">
            <div
              className="h-0.5 bg-blue-500 transition-all"
              style={{ width: `${Math.round((Object.keys(mcqAnswers).length + Object.keys(dissertations).filter(k => dissertations[k]).length) / session.questions.length * 100)}%` }}
            />
          </div>
        )}
      </div>
      <div className="mt-6" />

      {/* Submit confirmation dialog */}
      {showConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-xl mx-4">
            <h2 className="text-lg font-bold text-gray-900">Submit exam?</h2>
            <p className="mt-2 text-sm text-gray-500">
              You have answered {Object.keys(mcqAnswers).length} of {session.questions.filter(q => q.question_type === "mcq").length} MCQ questions
              {session.questions.some(q => q.question_type === "dissertation") && ` and ${Object.keys(dissertations).filter(k => dissertations[k]).length} of ${session.questions.filter(q => q.question_type === "dissertation").length} written questions`}.
              This cannot be undone.
            </p>
            <div className="mt-5 flex gap-3">
              <button onClick={() => setShowConfirm(false)} className="flex-1 rounded-xl border border-gray-200 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">
                Keep working
              </button>
              <button
                onClick={() => { setShowConfirm(false); handleSubmit(); }}
                className="flex-1 rounded-xl bg-blue-600 py-2 text-sm font-semibold text-white hover:bg-blue-700">
                Submit now
              </button>
            </div>
          </div>
        </div>
      )}


      {session.questions.length === 0 && (
        <p className="text-center py-12 text-gray-400 text-sm">No questions available for this exam.</p>
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

      {/* "You are being recorded" webcam badge — only shown when proctoring is active */}
      {isRemoteExam && proctoringSessionId && (
        <video
          ref={videoRef}
          autoPlay
          muted
          playsInline
          className="fixed bottom-4 right-4 w-32 h-24 rounded-lg border-2 border-green-500 z-50 object-cover"
          aria-label="Webcam proctoring feed"
        />
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
    <div className="mb-8 rounded-lg border bg-white shadow-sm p-6 space-y-4">
      <div className="flex items-center gap-2">
        <span className="rounded bg-gray-100 px-2 py-0.5 text-xs font-mono text-gray-500">Q{index}</span>
        <span
          className={`rounded px-2 py-0.5 text-xs font-medium
          ${question.question_type === "mcq" ? "bg-blue-100 text-blue-700" : "bg-purple-100 text-purple-700"}`}>
          {question.question_type.toUpperCase()}
        </span>
      </div>
      {question.title && <p className="font-medium text-sm">{question.title}</p>}
      <p className="text-sm text-gray-700">{question.description}</p>

      {question.question_type === "mcq" && question.options && (
        <div className="space-y-2">
          {question.options.map((opt, idx) => {
            const selected = mcqAnswer.includes(idx);
            return (
              <label
                key={idx}
                className={`flex items-center gap-3 rounded border p-3 cursor-pointer transition
                  ${selected ? "border-blue-400 bg-blue-50" : "border-gray-200 hover:bg-gray-50"}
                  ${submitted ? "cursor-default" : ""}`}>
                <input
                  type="radio"
                  name={`q-${question.id}`}
                  disabled={submitted}
                  checked={selected}
                  onChange={() => onMCQSelect(idx)}
                  className="accent-blue-600"
                />
                <span className="font-mono text-xs text-gray-400">{opt.label}.</span>
                <span className="text-sm">{opt.text}</span>
              </label>
            );
          })}
        </div>
      )}

      {question.question_type === "dissertation" && (
        <textarea
          rows={6}
          disabled={submitted}
          placeholder="Write your answer here…"
          className="w-full rounded border border-gray-300 p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 resize-y disabled:bg-gray-50"
          value={dissertationText}
          onChange={(e) => onDissertationChange(e.target.value)}
        />
      )}
    </div>
  );
}
