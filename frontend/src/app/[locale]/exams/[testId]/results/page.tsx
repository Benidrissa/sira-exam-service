"use client";

import { useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getDissertationReview, patchHumanScore } from "@/lib/api";
import { AuditLogPanel } from "@/components/AuditLogPanel";
import type { DissertationAnswer } from "@/types/exam";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { CheckCircle2, Clock, FileText, Home, Info, Award, User, Save, Pencil, X } from "lucide-react";
import { toast } from "sonner";
import { formatError } from "@/lib/formatError";
import { Skeleton } from "@/components/ui/skeleton";
import { usePaginatedList } from "@/hooks/usePaginatedList";
import { PaginationControls } from "@/components/PaginationControls";
import { Select } from "@/components/ui/select";

// ─── Role detection (same as NavBar) ────────────────────────────────────────
function getRoleFromCookie(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|; )access_token=([^;]*)/);
  if (!match) return null;
  try {
    const payload = JSON.parse(atob(decodeURIComponent(match[1]).split(".")[1]));
    return payload.role ?? null;
  } catch {
    return null;
  }
}

// ─── Teacher grading view ────────────────────────────────────────────────────
function TeacherGradingView({ testId, locale }: { testId: string; locale: string }) {
  const qc = useQueryClient();
  const router = useRouter();

  const hasPending = (answers: DissertationAnswer[]) =>
    answers.some((a) => a.status === "pending");

  const { data: answers, isLoading, error } = useQuery({
    queryKey: ["dissertation-review", testId],
    queryFn: () => getDissertationReview(testId),
    refetchInterval: (q) =>
      q.state.data && hasPending(q.state.data) ? 15_000 : false,
    staleTime: 10_000,
  });

  // Hook called unconditionally before any conditional returns
  const { page: gradingPage, total: gradingTotal, totalPages: gradingTotalPages,
    currentPage: gradingCurrentPage, setPage: setGradingPage, filters: gradingFilters, setFilter: setGradingFilter } =
    usePaginatedList<DissertationAnswer>(answers ?? [], {
      pageSize: 10,
      filterFn: (a, f) => !f.status || a.status === f.status,
    });

  if (isLoading) return (
    <main className="max-w-3xl mx-auto p-8 space-y-6">
      <Skeleton className="h-8 w-56" />
      {[1, 2].map(i => <Skeleton key={i} className="h-64 w-full rounded-xl" />)}
    </main>
  );
  if (error) return <p className="p-8 text-sm text-destructive">{formatError(error)}</p>;
  if (!answers || answers.length === 0) return (
    <div className="max-w-2xl mx-auto p-8 space-y-4">
      <p className="text-sm text-muted-foreground">Aucune réponse de dissertation en attente de correction.</p>
      <Button variant="outline" onClick={() => router.push(`/${locale}/`)}>
        <Home className="mr-2 h-4 w-4" /> Retour à l&apos;accueil
      </Button>
    </div>
  );

  return (
    <main className="max-w-3xl mx-auto p-8 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Notation des dissertations</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {answers.length} réponse{answers.length !== 1 ? "s" : ""} à corriger.
            {hasPending(answers) && " Actualisation automatique pendant la notation IA…"}
          </p>
        </div>
        <Select
          options={[
            { value: "pending", label: "Notation IA en attente" },
            { value: "ai_scored", label: "Noté par l'IA" },
            { value: "human_reviewed", label: "Revu par l'enseignant" },
          ]}
          placeholder="Tous les statuts"
          value={gradingFilters.status}
          onChange={e => setGradingFilter("status", e.target.value)}
          className="w-44"
        />
      </div>

      {gradingTotal === 0 && <p className="text-sm text-muted-foreground">Aucune réponse ne correspond à ce filtre.</p>}

      {gradingPage.map((answer, idx) => (
        <GradingCard
          key={answer.id}
          index={(gradingCurrentPage - 1) * 10 + idx + 1}
          answer={answer}
          onUpdated={(updated) => {
            qc.setQueryData<DissertationAnswer[]>(
              ["dissertation-review", testId],
              (old) => old?.map((a) => (a.id === updated.id ? updated : a)) ?? [],
            );
          }}
        />
      ))}

      <PaginationControls currentPage={gradingCurrentPage} totalPages={gradingTotalPages} totalItems={gradingTotal} pageSize={10} onPageChange={setGradingPage} />

      <div className="flex justify-center pt-4">
        <Button variant="outline" onClick={() => router.push(`/${locale}/`)}>
          <Home className="mr-2 h-4 w-4" /> Retour à l&apos;accueil
        </Button>
      </div>

      <AuditLogPanel testId={testId} />
    </main>
  );
}

function GradingCard({
  index, answer, onUpdated,
}: {
  index: number;
  answer: DissertationAnswer;
  onUpdated: (a: DissertationAnswer) => void;
}) {
  const [humanScore, setHumanScore] = useState(
    answer.human_score != null ? String(answer.human_score) : "",
  );
  const [humanFeedback, setHumanFeedback] = useState(answer.human_feedback ?? "");
  const [aiScoreOverride, setAiScoreOverride] = useState(
    answer.ai_score != null ? String(answer.ai_score) : "",
  );
  const [aiFeedbackOverride, setAiFeedbackOverride] = useState(answer.ai_feedback ?? "");
  const [isEditing, setIsEditing] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const buildPayload = () => {
    const payload: Parameters<typeof patchHumanScore>[1] = {
      human_score: Number(humanScore),
      human_feedback: humanFeedback,
    };
    const parsedAiScore = aiScoreOverride !== "" ? Number(aiScoreOverride) : null;
    if (parsedAiScore !== null && parsedAiScore !== answer.ai_score) {
      payload.ai_score_override = parsedAiScore;
    }
    if (aiFeedbackOverride !== answer.ai_feedback) {
      payload.ai_feedback_override = aiFeedbackOverride;
    }
    return payload;
  };

  const mutation = useMutation({
    mutationFn: () => patchHumanScore(answer.id, buildPayload()),
    onSuccess: (updated) => { onUpdated(updated); setSaveError(null); setIsEditing(false); toast.success("Note enregistrée"); },
    onError: (e) => { const msg = formatError(e); setSaveError(msg); toast.error(msg); },
  });

  const statusVariant = {
    pending: "warning",
    ai_scored: "info",
    human_reviewed: "success",
  } as const;

  const statusLabel = {
    pending: "Notation IA…",
    ai_scored: "Noté par l'IA",
    human_reviewed: "Revu par l'enseignant",
  }[answer.status];

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-4">
        <span className="text-sm font-medium text-muted-foreground">Réponse {index}</span>
        <Badge variant={statusVariant[answer.status]}>
          {answer.status === "human_reviewed" && <CheckCircle2 className="mr-1 h-3 w-3" />}
          {answer.status === "pending" && <LoadingSpinner className="mr-1 h-3 w-3" />}
          {statusLabel}
        </Badge>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Student answer */}
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <User className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Réponse de l&apos;étudiant
            </span>
          </div>
          <div className="bg-muted rounded-lg p-3 max-h-40 overflow-y-auto">
            <p className="text-sm whitespace-pre-wrap">{answer.answer_text}</p>
          </div>
        </div>

        <Separator />

        {/* AI scoring */}
        {answer.status === "pending" ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <LoadingSpinner className="h-4 w-4" /> Notation IA en cours…
          </div>
        ) : answer.ai_score != null && (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Award className="h-4 w-4 text-muted-foreground" />
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Note IA</span>
              <Badge variant="info" className="ml-1 font-mono">
                {answer.ai_score.toFixed(1)} / 100
              </Badge>
            </div>
            {answer.ai_feedback && (
              <div className="rounded-lg border bg-muted/30 px-3 py-2">
                <p className="text-xs font-medium text-muted-foreground mb-1">Commentaire IA</p>
                <p className="text-sm text-muted-foreground italic">{answer.ai_feedback}</p>
              </div>
            )}
          </div>
        )}

        <Separator />

        {/* Human override */}
        {answer.status === "human_reviewed" && !isEditing ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
              <span className="text-sm font-medium">Note finale : {answer.human_score} / 100</span>
              <Badge variant="success">Revu par l&apos;enseignant</Badge>
              <Button
                size="sm"
                variant="ghost"
                className="ml-auto h-7 px-2 text-xs"
                onClick={() => setIsEditing(true)}
              >
                <Pencil className="mr-1 h-3 w-3" /> Modifier
              </Button>
            </div>
            {answer.human_feedback && (
              <p className="text-sm text-muted-foreground italic">{answer.human_feedback}</p>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Note de l&apos;enseignant
            </p>
            <div className="flex items-center gap-3">
              <Label htmlFor={`score-${answer.id}`} className="text-sm shrink-0">
                Note (0–100)
              </Label>
              <Input
                id={`score-${answer.id}`}
                type="number" min={0} max={100} step={0.5}
                className="w-28"
                value={humanScore}
                onChange={(e) => setHumanScore(e.target.value)}
              />
            </div>
            <Textarea
              placeholder="Commentaire pour l'étudiant…"
              rows={3}
              value={humanFeedback}
              onChange={(e) => setHumanFeedback(e.target.value)}
            />

            <Separator />

            <div className="space-y-2">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Remplacer l&apos;évaluation IA (optionnel)
              </p>
              <div className="flex items-center gap-3">
                <Label htmlFor={`ai-score-${answer.id}`} className="text-sm shrink-0">
                  Note IA (0–100)
                </Label>
                <Input
                  id={`ai-score-${answer.id}`}
                  type="number" min={0} max={100} step={0.5}
                  className="w-28"
                  value={aiScoreOverride}
                  onChange={(e) => setAiScoreOverride(e.target.value)}
                />
              </div>
              <Textarea
                placeholder="Remplacer le commentaire IA…"
                rows={4}
                value={aiFeedbackOverride}
                onChange={(e) => setAiFeedbackOverride(e.target.value)}
              />
            </div>

            {saveError && <p className="text-xs text-destructive" role="alert">{saveError}</p>}
          </div>
        )}
      </CardContent>

      {(answer.status !== "human_reviewed" || isEditing) && (
        <CardFooter className="gap-2">
          <Button
            size="sm"
            disabled={!humanScore || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? <LoadingSpinner className="mr-2 h-4 w-4" /> : <Save className="mr-2 h-4 w-4" />}
            Enregistrer &amp; publier
          </Button>
          {isEditing && (
            <Button
              size="sm"
              variant="ghost"
              disabled={mutation.isPending}
              onClick={() => { setIsEditing(false); setSaveError(null); }}
            >
              <X className="mr-1 h-3 w-3" /> Annuler
            </Button>
          )}
        </CardFooter>
      )}
    </Card>
  );
}

// ─── Student results view ────────────────────────────────────────────────────
function StudentResultsView({ locale, score, total }: {
  locale: string;
  score: number | null;
  total: number | null;
}) {
  const router = useRouter();
  return (
    <main className="max-w-2xl mx-auto p-8 space-y-6">
      <div className="flex items-center gap-3">
        <CheckCircle2 className="h-8 w-8 text-emerald-500 shrink-0" />
        <div>
          <h1 className="text-2xl font-bold">Examen soumis</h1>
          <p className="text-sm text-muted-foreground">Vos réponses ont été enregistrées avec succès.</p>
        </div>
        <Badge variant="warning" className="ml-auto shrink-0">En attente de correction</Badge>
      </div>

      <Alert>
        <Info className="h-4 w-4" />
        <AlertDescription>
          Votre résultat final vous sera communiqué par votre enseignant une fois toute la notation — y compris
          la correction des réponses rédigées — terminée.
        </AlertDescription>
      </Alert>

      {score != null && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Notation automatique — QCM</CardTitle>
              <Badge variant="secondary" className="text-xs">Préliminaire</Badge>
            </div>
            <CardDescription>Les questions à choix multiples sont notées automatiquement.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-end gap-2">
              <span className="text-4xl font-bold tabular-nums">{score}</span>
              {total != null && (
                <span className="text-lg text-muted-foreground mb-1">/ {total} question{total !== 1 ? "s" : ""}</span>
              )}
            </div>
            {total != null && total > 0 && (
              <p className="mt-2 text-sm text-muted-foreground">
                {Math.round((score / total) * 100)}% de bonnes réponses
              </p>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex-row items-center gap-3 space-y-0">
          <FileText className="h-5 w-5 text-primary shrink-0" />
          <div>
            <CardTitle className="text-base">Réponses rédigées — Correction par l&apos;enseignant</CardTitle>
            <CardDescription>
              Vos dissertations sont d&apos;abord notées par l&apos;IA, puis revues et validées par votre enseignant.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-amber-500" />
            <Badge variant="warning">En attente de correction par l&apos;enseignant</Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            Votre enseignant vous communiquera vos notes et commentaires pour les réponses rédigées.
            C&apos;est l&apos;étape de notation de référence — le résultat final en dépend.
          </p>
        </CardContent>
      </Card>

      <Separator />
      <div className="flex justify-center">
        <Button variant="outline" onClick={() => router.push(`/${locale}/`)}>
          <Home className="mr-2 h-4 w-4" /> Retour à l&apos;accueil
        </Button>
      </div>
    </main>
  );
}

// ─── Router: detect role, render appropriate view ───────────────────────────
function ResultsContent() {
  const { testId, locale } = useParams<{ testId: string; locale?: string }>();
  const effectiveLocale = (locale as string) ?? "fr";
  const router = useRouter();
  const searchParams = useSearchParams();

  const attemptId = searchParams.get("attemptId");
  const score = searchParams.get("score") != null ? parseFloat(searchParams.get("score")!) : null;
  const total = searchParams.get("total") != null ? parseFloat(searchParams.get("total")!) : null;

  const role = getRoleFromCookie();

  // Teacher: show grading UI
  if (role === "expert") {
    return <TeacherGradingView testId={testId} locale={effectiveLocale} />;
  }

  // Student without attempt params: no results yet
  if (!attemptId) {
    return (
      <div className="flex justify-center mt-20">
        <Card className="w-full max-w-md text-center">
          <CardHeader>
            <CardTitle>Aucun résultat trouvé</CardTitle>
            <CardDescription>
              Cet examen n&apos;a pas encore été soumis, ou votre session a expiré.
            </CardDescription>
          </CardHeader>
          <CardFooter className="justify-center">
            <Button onClick={() => router.push(`/${effectiveLocale}/`)}>
              <Home className="mr-2 h-4 w-4" /> Retour à l&apos;accueil
            </Button>
          </CardFooter>
        </Card>
      </div>
    );
  }

  // Student: show results
  return <StudentResultsView locale={effectiveLocale} score={score} total={total} />;
}

export default function ResultsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex justify-center mt-20 text-sm text-muted-foreground">
          Chargement…
        </div>
      }
    >
      <ResultsContent />
    </Suspense>
  );
}
