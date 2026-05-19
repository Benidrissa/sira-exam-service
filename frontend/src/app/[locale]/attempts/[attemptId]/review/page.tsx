"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getAttemptReview, listAttemptComplaints, fileComplaint } from "@/lib/api";
import type { ReviewQuestionAnswer, ScoreComplaint } from "@/types/exam";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useParams } from "next/navigation";

function ComplaintSection({ attemptId, questionId, complaints }: { attemptId: string; questionId: string | null; complaints: ScoreComplaint[] }) {
  const qc = useQueryClient();
  const existing = complaints.find(c => c.question_id === questionId);
  const [reason, setReason] = useState("");
  const [open, setOpen] = useState(false);

  const mutation = useMutation({
    mutationFn: () => fileComplaint(attemptId, { question_id: questionId ?? undefined, reason }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["complaints", attemptId] }); setOpen(false); setReason(""); },
  });

  if (existing) {
    const color = existing.status === "approved" ? "bg-green-100 text-green-700" : existing.status === "rejected" ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700";
    return <Badge className={color}>{existing.status.charAt(0).toUpperCase() + existing.status.slice(1)}</Badge>;
  }

  return open ? (
    <div className="space-y-2 mt-2">
      <Textarea placeholder="Describe your dispute (min 20 chars)" value={reason} onChange={e => setReason(e.target.value)} rows={3} />
      <div className="flex gap-2">
        <Button size="sm" onClick={() => mutation.mutate()} disabled={reason.length < 20 || mutation.isPending}>
          {mutation.isPending ? "Submitting…" : "Submit"}
        </Button>
        <Button size="sm" variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
      </div>
    </div>
  ) : (
    <Button size="sm" variant="outline" onClick={() => setOpen(true)}>Dispute score</Button>
  );
}

export default function AttemptReviewPage() {
  const params = useParams();
  const attemptId = params.attemptId as string;

  const { data, isLoading, error } = useQuery({
    queryKey: ["attempt-review", attemptId],
    queryFn: () => getAttemptReview(attemptId),
  });

  const { data: complaints = [] } = useQuery({
    queryKey: ["complaints", attemptId],
    queryFn: () => listAttemptComplaints(attemptId),
    enabled: !!data?.feedback_available,
  });

  if (isLoading) return <div className="p-8">Loading…</div>;
  if (error || !data) return <p className="p-8 text-destructive">{String(error)}</p>;

  return (
    <main className="max-w-4xl mx-auto p-8 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Exam Review</h1>
        <div className="text-sm">
          Score: <span className="font-bold">{data.total_score?.toFixed(1) ?? "—"}</span>
          {data.passed != null && (
            <Badge className={`ml-2 ${data.passed ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
              {data.passed ? "Passed" : "Failed"}
            </Badge>
          )}
        </div>
      </div>

      {!data.feedback_available && (
        <Alert>
          <AlertDescription>
            Detailed feedback and correct answers will be available once the test closes.
          </AlertDescription>
        </Alert>
      )}

      {/* Total score complaint */}
      {data.feedback_available && data.validation_status === "validated" && (
        <Card>
          <CardContent className="py-4 flex items-center justify-between">
            <p className="text-sm font-medium">Dispute total score</p>
            <ComplaintSection attemptId={attemptId} questionId={null} complaints={complaints} />
          </CardContent>
        </Card>
      )}

      <div className="space-y-4">
        {data.questions.map((q: ReviewQuestionAnswer, i: number) => (
          <Card key={q.question_id}>
            <CardHeader>
              <CardTitle className="text-base">Q{i + 1} — {q.question_type === "mcq" ? "MCQ" : "Dissertation"}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm">{q.description}</p>

              {q.question_type === "mcq" && q.options && (
                <div className="space-y-1">
                  {q.options.map((opt, idx) => {
                    const selected = q.mcq_answer_indices?.includes(idx);
                    const correct = data.feedback_available && q.correct_answer_indices?.includes(idx);
                    return (
                      <p key={idx} className={`text-sm px-2 py-1 rounded ${correct ? "bg-green-100 text-green-800" : selected ? "bg-red-50 text-red-700" : ""}`}>
                        {opt.label}. {opt.text}
                        {correct && " (correct)"}
                        {selected && !correct && " (your answer)"}
                      </p>
                    );
                  })}
                </div>
              )}

              {q.question_type === "dissertation" && (
                <div className="space-y-2">
                  <div className="bg-muted/40 rounded p-3 text-sm">
                    <p className="font-medium mb-1">Your answer:</p>
                    <p className="whitespace-pre-wrap">{q.dissertation_answer_text ?? "—"}</p>
                  </div>
                  {data.feedback_available && (
                    <>
                      <div className="flex gap-4 text-sm">
                        {q.ai_score != null && <span className="text-blue-600">AI score: {q.ai_score}</span>}
                        {q.human_score != null && <span className="text-green-600">Final score: {q.human_score}</span>}
                      </div>
                      {q.ai_feedback && <p className="text-xs text-muted-foreground">{q.ai_feedback}</p>}
                    </>
                  )}
                </div>
              )}

              {/* Per-question complaint — only when feedback available and validated */}
              {data.feedback_available && data.validation_status === "validated" && (
                <div className="pt-2 border-t">
                  <ComplaintSection attemptId={attemptId} questionId={q.question_id} complaints={complaints} />
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </main>
  );
}
