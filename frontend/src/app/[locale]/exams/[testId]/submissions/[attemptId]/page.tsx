"use client";
import { useQuery } from "@tanstack/react-query";
import { getAttemptFullReview } from "@/lib/api";
import type { ReviewQuestionAnswer } from "@/types/exam";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useParams } from "next/navigation";
import Link from "next/link";
import { BackLink } from "@/components/BackLink";
import { formatError } from "@/lib/formatError";

export default function AttemptFullReviewPage() {
  const params = useParams();
  const attemptId = params.attemptId as string;
  const testId = params.testId as string;
  const locale = params.locale as string;

  const { data, isLoading, error } = useQuery({
    queryKey: ["attempt-full-review", attemptId],
    queryFn: () => getAttemptFullReview(attemptId),
  });

  if (isLoading) return <div className="p-8">Loading…</div>;
  if (error || !data) return <p className="p-8 text-destructive">{formatError(error)}</p>;

  return (
    <main className="max-w-4xl mx-auto p-8 space-y-6">
      <div className="flex items-center justify-between">
        <BackLink href={`/${locale}/exams/${testId}/submissions`} label="Submissions" />
        <Link href={`/${locale}/exams/${testId}/results`}>
          <Button variant="outline" size="sm">Open Grading Dashboard →</Button>
        </Link>
      </div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Student Attempt Review</h1>
        <div className="text-sm text-muted-foreground">
          <span>MCQ: {data.mcq_score?.toFixed(1) ?? "—"} </span>
          <span>| Total: {data.total_score?.toFixed(1) ?? "—"} </span>
          <span>| {data.passed ? "Passed" : "Not passed"}</span>
        </div>
      </div>

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
                    const correct = q.correct_answer_indices?.includes(idx);
                    return (
                      <p key={idx} className={`text-sm px-2 py-1 rounded ${correct ? "bg-green-100 text-green-800" : selected ? "bg-red-100 text-red-700" : ""}`}>
                        {opt.label}. {opt.text}
                        {correct && " (correct)"}
                        {selected && !correct && " (student)"}
                      </p>
                    );
                  })}
                </div>
              )}

              {q.question_type === "dissertation" && (
                <div className="space-y-2">
                  <div className="bg-muted/40 rounded p-3 text-sm">
                    <p className="font-medium mb-1">Student answer:</p>
                    <p className="whitespace-pre-wrap">{q.dissertation_answer_text ?? "—"}</p>
                  </div>
                  <div className="flex gap-4 text-sm">
                    {q.ai_score != null && <span className="text-blue-600">AI: {q.ai_score}</span>}
                    {q.human_score != null && <span className="text-green-600">Human: {q.human_score}</span>}
                  </div>
                  {q.ai_feedback && <p className="text-xs text-muted-foreground">{q.ai_feedback}</p>}
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </main>
  );
}
