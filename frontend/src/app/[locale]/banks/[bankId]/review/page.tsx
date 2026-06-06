"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams } from "next/navigation";
import {
  listScenarios,
  listQuestions,
  patchScenario,
  patchQuestion,
  validateQuestion,
  validateAll,
  apiFetch,
} from "@/lib/api";
import type { ExamScenario, ExamQuestion } from "@/types/exam";
import { useDebounce } from "@/hooks/use-debounce";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { cn } from "@/lib/utils";
import {
  CheckCircle2, ChevronDown, ChevronUp, Copy, Plus, Trash2, Check,
} from "lucide-react";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { toast } from "sonner";
import { formatError } from "@/lib/formatError";

// ─── API helpers not yet in api.ts ──────────────────────────────────────────
function createQuestion(
  bankId: string,
  data: {
    scenario_id: string | null;
    question_type: "mcq" | "dissertation";
    description: string;
    options?: Array<{ label: string; text: string }>;
    correct_answer_indices?: number[];
  },
): Promise<ExamQuestion> {
  return apiFetch<ExamQuestion>(`/exam/banks/${bankId}/question`, {
    method: "POST",
    body: JSON.stringify({ ...data, ai_generated: false, order_index: 9999 }),
  });
}

// ─── Main page ───────────────────────────────────────────────────────────────
export default function ReviewBoardPage() {
  const { bankId, locale } = useParams<{ bankId: string; locale: string }>();
  const [scenarios, setScenarios] = useState<ExamScenario[]>([]);
  const [questions, setQuestions] = useState<ExamQuestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [publishState, setPublishState] = useState<"idle" | "publishing" | "done" | "error">("idle");
  const [testLink, setTestLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [showPublishConfirm, setShowPublishConfirm] = useState(false);

  useEffect(() => {
    Promise.all([listScenarios(bankId), listQuestions(bankId)])
      .then(([sc, qs]) => { setScenarios(sc); setQuestions(qs); })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [bankId]);

  const questionsByScenario = useCallback(
    (scenarioId: string) =>
      questions
        .filter((q) => q.scenario_id === scenarioId)
        .sort((a, b) => a.order_index - b.order_index),
    [questions],
  );

  const unassignedQuestions = questions
    .filter((q) => q.scenario_id === null)
    .sort((a, b) => a.order_index - b.order_index);

  async function handleValidateAll() {
    setPublishState("publishing");
    try {
      await validateAll(bankId);
      const res = await apiFetch<{ id: string; status: string }[]>(
        `/exam/banks/${bankId}/tests`,
      );
      if (res.length) {
        const testId = res[0].id;
        const link = `${window.location.origin}/${locale}/exams/${testId}/play`;
        setTestLink(link);
      }
      setPublishState("done");
      toast.success("Banque d'examens publiée.");
    } catch (e) {
      const msg = formatError(e);
      setSaveError(msg);
      toast.error(msg);
      setPublishState("error");
    }
  }

  async function handleAddQuestion(scenarioId: string | null, type: "mcq" | "dissertation") {
    try {
      const defaultOptions =
        type === "mcq"
          ? [
              { label: "A", text: "Option A" },
              { label: "B", text: "Option B" },
              { label: "C", text: "Option C" },
              { label: "D", text: "Option D" },
            ]
          : undefined;
      const newQ = await createQuestion(bankId, {
        scenario_id: scenarioId,
        question_type: type,
        description: type === "mcq" ? "Nouvelle question QCM" : "Nouvelle question de dissertation",
        options: defaultOptions,
        correct_answer_indices: type === "mcq" ? [0] : undefined,
      });
      setQuestions((prev) => [...prev, newQ]);
    } catch (e) {
      setSaveError(`Échec de l'ajout de la question : ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  if (loading) return (
    <div className="flex items-center justify-center p-12 gap-2 text-sm text-muted-foreground">
      <LoadingSpinner className="h-4 w-4" /> Chargement du tableau de révision…
    </div>
  );
  if (error) return <p className="p-8 text-sm text-destructive">{error}</p>;

  const allValidated = questions.length > 0 && questions.every((q) => q.validated);
  const validatedCount = questions.filter((q) => q.validated).length;

  return (
    <div className="max-w-3xl mx-auto px-6 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Révision et modification</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {questions.length} questions · {scenarios.length} scénarios ·{" "}
            {validatedCount}/{questions.length} validées
          </p>
        </div>
        <div className="flex flex-col items-end gap-2 shrink-0">
          {saveError && (
            <p className="text-xs text-destructive max-w-xs text-right">{saveError}</p>
          )}
          {publishState === "done" && testLink ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground truncate max-w-48">{testLink}</span>
              <Button
                size="sm"
                variant="outline"
                onClick={() => { navigator.clipboard.writeText(testLink); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
              >
                {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
              </Button>
            </div>
          ) : (
            <>
              <Button
                disabled={publishState === "publishing"}
                onClick={() => setShowPublishConfirm(true)}
              >
                {publishState === "publishing" ? (
                  <><LoadingSpinner className="h-4 w-4" /> Publication…</>
                ) : allValidated ? "Publier la banque" : "Tout valider et publier"}
              </Button>
              <ConfirmDialog
                open={showPublishConfirm}
                title={allValidated ? "Publier cette banque d'examens ?" : "Valider et publier cette banque d'examens ?"}
                description="Les étudiants pourront accéder aux tests de cette banque. Cette action est irréversible."
                confirmLabel="Publier"
                onConfirm={() => { setShowPublishConfirm(false); handleValidateAll(); }}
                onCancel={() => setShowPublishConfirm(false)}
              />
            </>
          )}
        </div>
      </div>

      {/* Zero-questions warning */}
      {questions.length === 0 && (
        <Alert variant="warning">
          <AlertTitle>Aucune question</AlertTitle>
          <AlertDescription>Aucune question générée pour l&apos;instant. Revenez en arrière et lancez d&apos;abord la génération.</AlertDescription>
        </Alert>
      )}

      {/* Scenario cards */}
      {scenarios.map((scenario) => (
        <ScenarioCard
          key={scenario.id}
          bankId={bankId}
          scenario={scenario}
          questions={questionsByScenario(scenario.id)}
          onQuestionUpdate={(updated) =>
            setQuestions((prev) => prev.map((q) => q.id === updated.id ? updated : q))
          }
          onQuestionAdd={(type) => handleAddQuestion(scenario.id, type)}
          onSaveError={setSaveError}
        />
      ))}

      {scenarios.length === 0 && unassignedQuestions.length === 0 && (
        <p className="text-sm text-muted-foreground text-center py-12">
          Aucun scénario généré pour l&apos;instant.
        </p>
      )}

      {/* Questions without a scenario (null scenario_id) */}
      {unassignedQuestions.length > 0 && (
        <ScenarioCard
          key="__uncategorized__"
          bankId={bankId}
          scenario={{ id: "", bank_id: bankId, title: "Non catégorisé", objective: null, context_text: null, context_image_storage_key: null, order_index: 9999, created_at: "", updated_at: "" }}
          questions={unassignedQuestions}
          onQuestionUpdate={(updated) =>
            setQuestions((prev) => prev.map((q) => q.id === updated.id ? updated : q))
          }
          onQuestionAdd={(type) => handleAddQuestion(null, type)}
          onSaveError={setSaveError}
          readonlyTitle
        />
      )}
    </div>
  );
}

// ─── Scenario card ───────────────────────────────────────────────────────────
function ScenarioCard({
  bankId, scenario, questions, onQuestionUpdate, onQuestionAdd, onSaveError, readonlyTitle,
}: {
  bankId: string;
  scenario: ExamScenario;
  questions: ExamQuestion[];
  onQuestionUpdate: (q: ExamQuestion) => void;
  onQuestionAdd: (type: "mcq" | "dissertation") => void;
  onSaveError: (msg: string) => void;
  readonlyTitle?: boolean;
}) {
  const [title, setTitle] = useState(scenario.title);
  const [saving, setSaving] = useState(false);

  const saveTitle = useDebounce(
    useCallback(async (val: string) => {
      if (!scenario.id) return;
      setSaving(true);
      try { await patchScenario(bankId, scenario.id, { title: val }); }
      catch (e) { onSaveError(`Échec de la sauvegarde du scénario : ${e instanceof Error ? e.message : String(e)}`); }
      finally { setSaving(false); }
    }, [bankId, scenario.id, onSaveError]),
    600,
  );

  return (
    <Card className="mb-4">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-3">
          {readonlyTitle ? (
            <span className="flex-1 font-bold text-base px-2 text-muted-foreground italic">{title}</span>
          ) : (
            <Input
              className="flex-1 border-transparent bg-transparent font-bold text-base hover:border-input focus:border-input px-2"
              value={title}
              onChange={(e) => { setTitle(e.target.value); saveTitle(e.target.value); }}
            />
          )}
          {saving && <span className="text-xs text-muted-foreground shrink-0">Enregistrement…</span>}
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
            <p className="py-4 text-center text-xs text-muted-foreground">Aucune question dans ce scénario</p>
          )}
        </div>

        {/* Add question buttons */}
        <div className="flex items-center gap-2 px-5 py-3 border-t border-border">
          <Button
            size="sm" variant="ghost"
            className="text-xs text-muted-foreground hover:text-foreground"
            onClick={() => onQuestionAdd("mcq")}
          >
            <Plus className="h-3.5 w-3.5 mr-1" /> Ajouter un QCM
          </Button>
          <Button
            size="sm" variant="ghost"
            className="text-xs text-muted-foreground hover:text-foreground"
            onClick={() => onQuestionAdd("dissertation")}
          >
            <Plus className="h-3.5 w-3.5 mr-1" /> Ajouter une dissertation
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Question row ─────────────────────────────────────────────────────────────
function QuestionRow({
  bankId, question, onUpdate, onSaveError,
}: {
  bankId: string;
  question: ExamQuestion;
  onUpdate: (q: ExamQuestion) => void;
  onSaveError: (msg: string) => void;
}) {
  const [description, setDescription] = useState(question.description);
  const [options, setOptions] = useState<Array<{ label: string; text: string }>>(
    question.options ?? [],
  );
  const [correctIndices, setCorrectIndices] = useState<number[]>(
    question.correct_answer_indices ?? [],
  );
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);
  const [rubricOpen, setRubricOpen] = useState(false);

  // Patch helper — debounced for text edits, immediate for structural changes
  async function patch(data: Partial<{
    description: string;
    options: typeof options;
    correct_answer_indices: number[];
  }>) {
    setSaving(true);
    try {
      const updated = await patchQuestion(question.id, bankId, data);
      onUpdate(updated);
    } catch (e) {
      onSaveError(`Échec de l'enregistrement : ${e instanceof Error ? e.message : String(e)}`);
    } finally { setSaving(false); }
  }

  const saveDescription = useDebounce(
    useCallback((val: string) => patch({ description: val }), [question.id, bankId]),
    600,
  );

  // Toggle correct answer for MCQ
  async function toggleCorrect(idx: number) {
    const next = correctIndices.includes(idx)
      ? correctIndices.filter((i) => i !== idx)
      : [...correctIndices, idx];
    setCorrectIndices(next);
    await patch({ correct_answer_indices: next });
  }

  // Edit option text
  async function saveOptionText(idx: number, text: string) {
    const next = options.map((o, i) => i === idx ? { ...o, text } : o);
    setOptions(next);
    await patch({ options: next });
  }

  // Add new MCQ option
  async function addOption() {
    const labels = ["A", "B", "C", "D", "E", "F"];
    const label = labels[options.length] ?? String(options.length + 1);
    const next = [...options, { label, text: "Nouvelle option" }];
    setOptions(next);
    await patch({ options: next });
  }

  // Remove MCQ option
  async function removeOption(idx: number) {
    const next = options.filter((_, i) => i !== idx);
    const newCorrect = correctIndices.filter((i) => i !== idx).map((i) => i > idx ? i - 1 : i);
    setOptions(next);
    setCorrectIndices(newCorrect);
    await patch({ options: next, correct_answer_indices: newCorrect });
  }

  async function handleValidate() {
    setValidating(true);
    try {
      const updated = await validateQuestion(question.id, bankId);
      onUpdate(updated);
    } catch (e) {
      onSaveError(`Échec de la validation : ${e instanceof Error ? e.message : String(e)}`);
    } finally { setValidating(false); }
  }

  return (
    <div className="px-5 py-4 space-y-3">
      {/* Header row: badge + textarea + validate */}
      <div className="flex items-start gap-3">
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
            onChange={(e) => {
              setDescription(e.target.value);
              saveDescription(e.target.value);
            }}
          />
        </div>
        <div className="flex flex-col items-end gap-1.5 shrink-0">
          {saving && <span className="text-xs text-muted-foreground">Enregistrement…</span>}
          {question.validated ? (
            <Badge variant="success">
              <CheckCircle2 className="mr-1 h-3 w-3" /> Validé
            </Badge>
          ) : (
            <Button size="sm" variant="outline" onClick={handleValidate} disabled={validating}>
              {validating ? <LoadingSpinner className="h-3 w-3" /> : "Valider"}
            </Button>
          )}
        </div>
      </div>

      {/* MCQ options — editable, correct-answer clickable */}
      {question.question_type === "mcq" && (
        <div className="ml-16 space-y-1.5">
          {options.map((opt, i) => {
            const isCorrect = correctIndices.includes(i);
            return (
              <div key={i} className="flex items-center gap-2 group">
                {/* Correct-answer toggle */}
                <button
                  title={isCorrect ? "Marquer comme incorrect" : "Marquer comme bonne réponse"}
                  onClick={() => toggleCorrect(i)}
                  className={cn(
                    "h-4 w-4 rounded-full border-2 flex items-center justify-center shrink-0 transition-colors",
                    isCorrect
                      ? "border-emerald-500 bg-emerald-500 text-white"
                      : "border-muted-foreground/40 hover:border-emerald-400",
                  )}
                >
                  {isCorrect && <Check className="h-2.5 w-2.5" />}
                </button>
                {/* Option label */}
                <span className={cn(
                  "text-xs font-mono shrink-0 w-4",
                  isCorrect ? "text-emerald-600 font-bold" : "text-muted-foreground",
                )}>
                  {opt.label}.
                </span>
                {/* Option text — inline editable */}
                <input
                  className={cn(
                    "flex-1 text-xs bg-transparent border-0 border-b border-transparent",
                    "hover:border-muted-foreground/30 focus:border-primary focus:outline-none",
                    "transition-colors py-0",
                    isCorrect ? "text-emerald-600 font-medium" : "text-foreground",
                  )}
                  value={opt.text}
                  onChange={(e) => {
                    const updated = options.map((o, j) => j === i ? { ...o, text: e.target.value } : o);
                    setOptions(updated);
                  }}
                  onBlur={(e) => saveOptionText(i, e.target.value)}
                />
                {/* Remove option */}
                <button
                  title="Supprimer l'option"
                  onClick={() => removeOption(i)}
                  className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive transition-all"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            );
          })}
          {/* Add option */}
          {options.length < 6 && (
            <button
              onClick={addOption}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-primary transition-colors mt-1"
            >
              <Plus className="h-3 w-3" /> Ajouter une option
            </button>
          )}
        </div>
      )}

      {/* Dissertation rubric (collapsible, read-only) */}
      {question.question_type === "dissertation" && question.rubric && question.rubric.length > 0 && (
        <div className="ml-16">
          <button
            onClick={() => setRubricOpen((o) => !o)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            {rubricOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            Barème ({question.rubric.length} critères)
          </button>
          {rubricOpen && (
            <div className="mt-2 space-y-1.5">
              {question.rubric.map((r, i) => (
                <div key={i} className="flex items-center justify-between rounded-lg border bg-muted/40 px-3 py-2">
                  <span className="text-xs font-medium">{r.criterion}</span>
                  <span className="text-xs font-mono border rounded-full bg-background px-2 py-0.5">
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
