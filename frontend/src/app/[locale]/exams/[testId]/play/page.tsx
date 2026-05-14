"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { startAttempt, submitAttempt, startProctoringSession, terminateSession } from "@/lib/api";
import type { ExamQuestion, StartAttemptResponse } from "@/types/exam";
import { useLockdownShell } from "@/hooks/useLockdownShell";
import { useWebcamProctor } from "@/hooks/useWebcamProctor";

export default function ExamPlayerPage() {
  const { testId } = useParams<{ testId: string }>();
  const router = useRouter();
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
        }
      }

      setSubmitted(true);
      router.push(`/exams/${testId}/results`);
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
      <div className="sticky top-0 z-10 flex items-center justify-between bg-white border-b py-3 mb-6">
        <h1 className="text-lg font-semibold">Exam</h1>
        {secondsLeft !== null && (
          <span className={`font-mono text-xl font-bold ${timerColor}`}>{fmt(secondsLeft)}</span>
        )}
        <button
          disabled={submitting || submitted}
          onClick={handleSubmit}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
          {submitting ? "Submitting…" : submitted ? "Submitted ✓" : "Submit"}
        </button>
      </div>

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
