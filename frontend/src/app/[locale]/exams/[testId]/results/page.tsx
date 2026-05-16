"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getDissertationReview, patchHumanScore } from "@/lib/api";
import type { DissertationAnswer } from "@/types/exam";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { CheckCircle2, Award, User } from "lucide-react";

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

  if (isLoading) return (
    <div className="flex items-center gap-2 p-8 text-sm text-muted-foreground">
      <LoadingSpinner className="h-4 w-4" />
      Loading review queue…
    </div>
  );
  if (error) return <p className="p-8 text-sm text-destructive">{String(error)}</p>;
  if (!answers || answers.length === 0)
    return (
      <p className="p-8 text-sm text-muted-foreground">
        No dissertation answers pending review.
      </p>
    );

  return (
    <main className="max-w-3xl mx-auto p-8 space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold">Dissertation Grading</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {answers.length} answer{answers.length !== 1 ? "s" : ""} pending review.
          {hasPending(answers) && " Auto-refreshing every 30 s while AI is grading."}
        </p>
      </div>

      {answers.map((answer, idx) => (
        <AnswerCard
          key={answer.id}
          answerIndex={idx + 1}
          answer={answer}
          onUpdated={(updated) => {
            qc.setQueryData<DissertationAnswer[]>(
              ["dissertation-review", testId],
              (old) => old?.map((a) => a.id === updated.id ? updated : a) ?? [],
            );
          }}
        />
      ))}
    </main>
  );
}

function AnswerCard({ answerIndex, answer, onUpdated }: {
  answerIndex: number;
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

  const statusVariant = {
    pending: "warning",
    ai_scored: "info",
    human_reviewed: "success",
  } as const;

  const statusLabel = {
    pending: "Pending",
    ai_scored: "AI Scored",
    human_reviewed: "Human Reviewed",
  }[answer.status];

  return (
    <Card>
      {/* Card header */}
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-4">
        <span className="text-sm font-medium text-muted-foreground">
          Answer {answerIndex}
        </span>
        <Badge variant={statusVariant[answer.status]}>
          {answer.status === "human_reviewed" && <CheckCircle2 className="mr-1 h-3 w-3" />}
          {statusLabel}
        </Badge>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Student answer */}
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <User className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Student Answer
            </span>
          </div>
          <div className="bg-muted rounded-lg p-3 max-h-48 overflow-y-auto">
            <p className="text-sm whitespace-pre-wrap">{answer.answer_text}</p>
          </div>
        </div>

        <Separator />

        {/* AI scoring section */}
        {answer.status === "pending" ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <LoadingSpinner className="h-4 w-4" />
            AI grading in progress…
          </div>
        ) : answer.ai_score !== null && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Award className="h-4 w-4 text-muted-foreground" />
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                AI Score
              </span>
              <Badge variant="info" className="ml-1 font-mono text-sm px-2.5 py-0.5">
                {answer.ai_score.toFixed(1)} / 100
              </Badge>
            </div>

            {answer.criterion_scores && Object.keys(answer.criterion_scores).length > 0 && (
              <div className="space-y-1.5">
                <p className="text-xs text-muted-foreground">Criterion breakdown</p>
                <div className="grid gap-1.5">
                  {Object.entries(answer.criterion_scores).map(([k, v]) => (
                    <div
                      key={k}
                      className="flex items-center justify-between rounded-lg border border-border bg-muted/40 px-3 py-2"
                    >
                      <span className="text-xs text-foreground">{k}</span>
                      <span className="text-xs font-medium font-mono">{v}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {answer.ai_feedback && (
              <div className="rounded-lg border border-border bg-muted/30 px-3 py-2">
                <p className="text-xs font-medium text-muted-foreground mb-1">AI Feedback</p>
                <p className="text-sm text-muted-foreground italic">{answer.ai_feedback}</p>
              </div>
            )}
          </div>
        )}

        <Separator />

        {/* Human override */}
        <div className="space-y-3">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Teacher Override
          </p>

          <div className="flex items-center gap-3">
            <Label htmlFor={`score-${answer.id}`} className="text-sm shrink-0">
              Score (0–100)
            </Label>
            <Input
              id={`score-${answer.id}`}
              type="number"
              min={0}
              max={100}
              step={0.5}
              className="w-28"
              value={humanScore}
              onChange={(e) => setHumanScore(e.target.value)}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor={`feedback-${answer.id}`} className="text-sm">
              Feedback for student
            </Label>
            <Textarea
              id={`feedback-${answer.id}`}
              rows={3}
              placeholder="Feedback for student…"
              value={humanFeedback}
              onChange={(e) => setHumanFeedback(e.target.value)}
            />
          </div>

          {saveError && <p className="text-xs text-destructive">{saveError}</p>}

          <div className="flex items-center gap-3">
            <Button
              disabled={mutation.isPending || !humanScore}
              onClick={() => mutation.mutate()}
            >
              {mutation.isPending ? (
                <>
                  <LoadingSpinner className="h-4 w-4" />
                  Saving…
                </>
              ) : answer.status === "human_reviewed" ? "Update Grade" : "Submit Grade"}
            </Button>

            {/* Final score if human reviewed */}
            {answer.status === "human_reviewed" && answer.human_score !== null && (
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                <span className="text-sm text-muted-foreground">Final score:</span>
                <Badge variant="success" className="font-mono text-sm px-2.5 py-0.5">
                  {answer.human_score} / 100
                </Badge>
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
