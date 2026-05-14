"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getDissertationReview, patchHumanScore } from "@/lib/api";
import type { DissertationAnswer } from "@/types/exam";

export default function DissertationGradingPage() {
  const { testId } = useParams<{ testId: string }>();
  const qc = useQueryClient();

  const hasPending = (answers: DissertationAnswer[]) =>
    answers.some((a) => a.status === "pending");

  const { data: answers, isLoading, error } = useQuery({
    queryKey: ["dissertation-review", testId],
    queryFn: () => getDissertationReview(testId),
    refetchInterval: (query) =>
      query.state.data && hasPending(query.state.data) ? 30_000 : false,
    staleTime: 10_000,
  });

  if (isLoading) return <p className="p-8 text-sm text-gray-500">Loading review queue…</p>;
  if (error) return <p className="p-8 text-sm text-red-600">{String(error)}</p>;
  if (!answers || answers.length === 0)
    return <p className="p-8 text-sm text-gray-400">No dissertation answers pending review.</p>;

  return (
    <main className="max-w-3xl mx-auto p-8 space-y-6">
      <h1 className="text-2xl font-bold">Dissertation Grading</h1>
      <p className="text-sm text-gray-500">
        {answers.length} answer{answers.length !== 1 ? "s" : ""} pending review.
        {hasPending(answers) && " Auto-refreshing every 30 s while AI is grading."}
      </p>
      {answers.map((answer) => (
        <AnswerCard key={answer.id} answer={answer} onUpdated={(updated) => {
          qc.setQueryData<DissertationAnswer[]>(
            ["dissertation-review", testId],
            (old) => old?.map((a) => a.id === updated.id ? updated : a) ?? [],
          );
        }} />
      ))}
    </main>
  );
}

function AnswerCard({ answer, onUpdated }: {
  answer: DissertationAnswer;
  onUpdated: (a: DissertationAnswer) => void;
}) {
  const [humanScore, setHumanScore] = useState<string>(
    answer.human_score !== null ? String(answer.human_score) : "",
  );
  const [humanFeedback, setHumanFeedback] = useState(answer.human_feedback ?? "");
  const [saveError, setSaveError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => patchHumanScore(answer.id, {
      human_score: Number(humanScore),
      human_feedback: humanFeedback,
    }),
    onSuccess: (updated) => { onUpdated(updated); setSaveError(null); },
    onError: (e) => setSaveError(String(e)),
  });

  const statusColor = {
    pending: "bg-yellow-100 text-yellow-700",
    ai_scored: "bg-blue-100 text-blue-700",
    human_reviewed: "bg-green-100 text-green-700",
  }[answer.status];

  return (
    <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b bg-gray-50 px-4 py-3">
        <span className="text-xs text-gray-500 font-mono">Answer {answer.id.slice(0, 8)}</span>
        <span className={`rounded px-2 py-0.5 text-xs font-medium ${statusColor}`}>
          {answer.status.replace("_", " ")}
        </span>
      </div>

      {/* Student answer */}
      <div className="p-4 border-b">
        <p className="text-xs font-medium text-gray-400 mb-1">Student answer</p>
        <p className="text-sm whitespace-pre-wrap text-gray-700">{answer.answer_text}</p>
      </div>

      {/* AI grading */}
      {answer.status === "pending" && (
        <div className="p-4 border-b text-sm text-gray-400 flex items-center gap-2">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-blue-200 border-t-blue-500" />
          AI grading in progress…
        </div>
      )}
      {answer.ai_score !== null && (
        <div className="p-4 border-b space-y-2">
          <div className="flex items-center gap-3">
            <p className="text-xs font-medium text-gray-400">AI Score</p>
            <span className="rounded bg-blue-100 px-2 py-0.5 text-sm font-bold text-blue-700">
              {answer.ai_score.toFixed(1)} / 100
            </span>
          </div>
          {answer.criterion_scores && Object.keys(answer.criterion_scores).length > 0 && (
            <div className="space-y-1">
              <p className="text-xs text-gray-400">Criterion breakdown</p>
              {Object.entries(answer.criterion_scores).map(([k, v]) => (
                <div key={k} className="flex items-center justify-between text-xs">
                  <span className="text-gray-600">{k}</span>
                  <span className="font-medium">{v}</span>
                </div>
              ))}
            </div>
          )}
          {answer.ai_feedback && (
            <div>
              <p className="text-xs font-medium text-gray-400 mb-1">AI Feedback</p>
              <p className="text-sm text-gray-600 italic">{answer.ai_feedback}</p>
            </div>
          )}
        </div>
      )}

      {/* Human override */}
      <div className="p-4 space-y-3">
        <p className="text-xs font-medium text-gray-500">Teacher override</p>
        <div className="flex items-center gap-3">
          <label className="text-xs text-gray-500">Score (0–100)</label>
          <input type="number" min={0} max={100} step={0.5}
            className="w-24 rounded border border-gray-300 px-2 py-1 text-sm"
            value={humanScore}
            onChange={(e) => setHumanScore(e.target.value)} />
          {answer.human_score !== null && (
            <span className="text-xs text-green-600">Current: {answer.human_score}</span>
          )}
        </div>
        <textarea rows={3} placeholder="Feedback for student…"
          className="w-full rounded border border-gray-300 px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-400"
          value={humanFeedback}
          onChange={(e) => setHumanFeedback(e.target.value)} />
        {saveError && <p className="text-xs text-red-500">{saveError}</p>}
        <button
          disabled={mutation.isPending || !humanScore}
          onClick={() => mutation.mutate()}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
          {mutation.isPending ? "Saving…" :
           answer.status === "human_reviewed" ? "Update Grade" : "Submit Grade"}
        </button>
      </div>
    </div>
  );
}
