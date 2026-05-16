"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  listScenarios,
  listQuestions,
  patchScenario,
  patchQuestion,
  validateQuestion,
  validateAll,
} from "@/lib/api";
import type { ExamScenario, ExamQuestion } from "@/types/exam";
import { useDebounce } from "@/hooks/use-debounce";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { cn } from "@/lib/utils";
import { CheckCircle2, ChevronDown, ChevronUp, Copy } from "lucide-react";

export default function ReviewBoardPage() {
  const { bankId, locale } = useParams<{ bankId: string; locale: string }>();
  const router = useRouter();
  const [scenarios, setScenarios] = useState<ExamScenario[]>([]);
  const [questions, setQuestions] = useState<ExamQuestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [publishState, setPublishState] = useState<"idle" | "publishing" | "done" | "error">("idle");
  const [testLink, setTestLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    Promise.all([listScenarios(bankId), listQuestions(bankId)])
      .then(([sc, qs]) => { setScenarios(sc); setQuestions(qs); })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [bankId]);

  const questionsByScenario = useCallback((scenarioId: string) =>
    questions.filter((q) => q.scenario_id === scenarioId)
      .sort((a, b) => a.order_index - b.order_index),
    [questions]);

  async function handleValidateAll() {
    setPublishState("publishing");
    try {
      await validateAll(bankId);
      setPublishState("done");
      setQuestions((qs) => qs.map((q) => ({ ...q, validated: true })));
      try {
        const API = process.env.NEXT_PUBLIC_EXAM_API_URL ?? "http://localhost:8001/api/v1";
        let tests = await (await fetch(`${API}/exam/banks/${bankId}/tests`, { credentials: "include" })).json();
        if (!tests.length) {
          const res = await fetch(`${API}/exam/banks/${bankId}/tests`, {
            method: "POST", credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title: "Exam", time_limit_minutes: 60, shuffle_questions: true }),
          });
          tests = [await res.json()];
        }
        if (tests[0]?.id) {
          setTestLink(`${window.location.origin}/${locale}/exams/${tests[0].id}/play`);
        }
      } catch { /* ignore — bank is published even if test link fetch fails */ }
    } catch (e) {
      setError(String(e));
      setPublishState("error");
    }
  }

  async function handleCopy() {
    if (!testLink) return;
    await navigator.clipboard.writeText(testLink);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (loading) return (
    <main className="max-w-3xl mx-auto p-8">
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-32 animate-pulse rounded-xl bg-muted" />
        ))}
      </div>
    </main>
  );

  if (error) return (
    <main className="max-w-3xl mx-auto p-8">
      <Alert variant="destructive">
        <AlertTitle>Failed to load</AlertTitle>
        <AlertDescription>
          {error}
          <button onClick={() => router.back()} className="mt-2 block text-sm underline">
            Go back
          </button>
        </AlertDescription>
      </Alert>
    </main>
  );

  const allValidated = questions.length > 0 && questions.every((q) => q.validated);

  return (
    <main className="max-w-3xl mx-auto p-6 pb-12 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold">Review &amp; Edit</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {questions.length} questions · {scenarios.length} scenarios
          </p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          {saveError && (
            <Alert variant="destructive" className="py-2 px-3 text-xs w-auto">
              <AlertDescription>{saveError}</AlertDescription>
            </Alert>
          )}
          {publishState === "done" ? (
            <Badge variant="success" className="text-sm px-3 py-1.5 rounded-lg">
              <CheckCircle2 className="mr-1.5" />
              Published
            </Badge>
          ) : (
            <Button
              disabled={publishState === "publishing" || questions.length === 0}
              onClick={handleValidateAll}
            >
              {publishState === "publishing" ? (
                <>
                  <LoadingSpinner className="mr-1.5 h-4 w-4" />
                  Publishing…
                </>
              ) : allValidated ? "Publish Bank" : "Validate All & Publish"}
            </Button>
          )}
        </div>
      </div>

      {/* Test link banner after publish */}
      {testLink && (
        <Alert variant="success">
          <CheckCircle2 className="h-4 w-4" />
          <AlertTitle>Bank published! Share this link with students:</AlertTitle>
          <AlertDescription>
            <div className="flex items-center gap-2 mt-2">
              <code className="flex-1 rounded-lg border border-emerald-200 bg-white/60 px-3 py-1.5 text-xs truncate">
                {testLink}
              </code>
              <Button size="sm" variant="outline" onClick={handleCopy} className="shrink-0">
                <Copy className="mr-1 h-3 w-3" />
                {copied ? "Copied!" : "Copy"}
              </Button>
            </div>
          </AlertDescription>
        </Alert>
      )}

      {/* Zero-questions warning */}
      {questions.length === 0 && (
        <Alert variant="warning">
          <AlertTitle>No questions yet</AlertTitle>
          <AlertDescription>
            No questions generated yet. Go back and trigger generation first.
          </AlertDescription>
        </Alert>
      )}

      {/* Scenario cards */}
      {scenarios.map((scenario) => (
        <ScenarioCard
          key={scenario.id}
          bankId={bankId}
          onSaveError={(msg) => { setSaveError(msg); setTimeout(() => setSaveError(null), 3000); }}
          scenario={scenario}
          questions={questionsByScenario(scenario.id)}
          onQuestionUpdate={(updated) =>
            setQuestions((qs) => qs.map((q) => q.id === updated.id ? updated : q))}
        />
      ))}

      {scenarios.length === 0 && (
        <p className="text-sm text-muted-foreground text-center py-12">No scenarios generated yet.</p>
      )}
    </main>
  );
}

function ScenarioCard({ bankId, scenario, questions, onQuestionUpdate, onSaveError }: {
  bankId: string;
  scenario: ExamScenario;
  questions: ExamQuestion[];
  onQuestionUpdate: (q: ExamQuestion) => void;
  onSaveError: (msg: string) => void;
}) {
  const [title, setTitle] = useState(scenario.title);
  const [saving, setSaving] = useState(false);

  const saveTitle = useDebounce(
    useCallback(async (val: string) => {
      setSaving(true);
      try { await patchScenario(bankId, scenario.id, { title: val }); }
      catch (e) { onSaveError(`Failed to save scenario: ${e instanceof Error ? e.message : String(e)}`); }
      finally { setSaving(false); }
    }, [bankId, scenario.id, onSaveError]),
    600,
  );

  function handleTitleChange(val: string) {
    setTitle(val);
    saveTitle(val);
  }

  return (
    <Card className="mb-4">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-3">
          <Input
            className="flex-1 border-transparent bg-transparent font-bold text-base hover:border-input focus:border-input px-2"
            value={title}
            onChange={(e) => handleTitleChange(e.target.value)}
          />
          {saving && <span className="text-xs text-muted-foreground shrink-0">Saving…</span>}
        </div>
      </CardHeader>
      <CardContent className="pt-0 px-0 pb-0">
        <div className="divide-y divide-border">
          {questions.map((q) => (
            <QuestionRow
              key={q.id}
              bankId={bankId}
              question={q}
              onUpdate={onQuestionUpdate}
              onSaveError={onSaveError}
            />
          ))}
          {questions.length === 0 && (
            <p className="py-4 text-center text-xs text-muted-foreground">No questions</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function QuestionRow({ bankId, question, onUpdate, onSaveError }: {
  bankId: string;
  question: ExamQuestion;
  onUpdate: (q: ExamQuestion) => void;
  onSaveError: (msg: string) => void;
}) {
  const [description, setDescription] = useState(question.description);
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);
  const [rubricOpen, setRubricOpen] = useState(false);

  const saveDescription = useDebounce(
    useCallback(async (val: string) => {
      setSaving(true);
      try {
        const updated = await patchQuestion(question.id, bankId, { description: val });
        onUpdate(updated);
      } catch (e) {
        onSaveError(`Failed to save question: ${e instanceof Error ? e.message : String(e)}`);
      } finally { setSaving(false); }
    }, [question.id, bankId, onUpdate, onSaveError]),
    600,
  );

  async function handleValidate() {
    setValidating(true);
    try {
      const updated = await validateQuestion(question.id, bankId);
      onUpdate(updated);
    } catch (e) {
      onSaveError(`Failed to validate: ${e instanceof Error ? e.message : String(e)}`);
    } finally { setValidating(false); }
  }

  return (
    <div className="px-5 py-4 space-y-3">
      {/* Main row */}
      <div className="flex items-start gap-3">
        {/* Left: badge + textarea */}
        <div className="flex-1 flex items-start gap-3 min-w-0">
          <Badge
            variant={question.question_type === "mcq" ? "info" : "purple"}
            className="mt-0.5 shrink-0"
          >
            {question.question_type.toUpperCase()}
          </Badge>
          <Textarea
            rows={2}
            className="flex-1 min-w-0 border-transparent bg-transparent text-sm hover:border-input focus:border-input resize-none"
            value={description}
            onChange={(e) => { setDescription(e.target.value); saveDescription(e.target.value); }}
          />
        </div>
        {/* Right: saving indicator + validate */}
        <div className="flex flex-col items-end gap-1.5 shrink-0">
          {saving && <span className="text-xs text-muted-foreground">Saving…</span>}
          {question.validated ? (
            <Badge variant="success">
              <CheckCircle2 className="mr-1" />
              Validated
            </Badge>
          ) : (
            <Button
              size="sm"
              variant="outline"
              onClick={handleValidate}
              disabled={validating}
            >
              {validating ? <LoadingSpinner className="h-3 w-3" /> : "Validate"}
            </Button>
          )}
        </div>
      </div>

      {/* MCQ options */}
      {question.question_type === "mcq" && question.options && (
        <ul className="ml-16 space-y-1">
          {question.options.map((opt, i) => {
            const isCorrect = (question.correct_answer_indices ?? []).includes(i);
            return (
              <li
                key={i}
                className={cn(
                  "flex items-center gap-2 text-xs",
                  isCorrect ? "text-emerald-600 font-medium" : "text-muted-foreground",
                )}
              >
                <span className="h-1.5 w-1.5 rounded-full bg-current shrink-0" />
                <span className="font-mono">{opt.label}.</span>
                {opt.text}
                {isCorrect && <span className="ml-0.5">✓</span>}
              </li>
            );
          })}
        </ul>
      )}

      {/* Dissertation rubric (collapsible) */}
      {question.question_type === "dissertation" && question.rubric && question.rubric.length > 0 && (
        <div className="ml-16">
          <button
            onClick={() => setRubricOpen((o) => !o)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            {rubricOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            Rubric ({question.rubric.length} criteria)
          </button>
          {rubricOpen && (
            <div className="mt-2 space-y-1.5">
              {question.rubric.map((r, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between rounded-lg border border-border bg-muted/40 px-3 py-2"
                >
                  <span className="text-xs font-medium text-foreground">{r.criterion}</span>
                  <span className="text-xs rounded-full border border-border bg-background px-2 py-0.5 font-mono">
                    {r.max_points} pts
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
