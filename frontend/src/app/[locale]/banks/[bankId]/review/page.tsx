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
} from "@/lib/api";
import type { ExamScenario, ExamQuestion } from "@/types/exam";
import { useDebounce } from "@/hooks/use-debounce";

export default function ReviewBoardPage() {
  const { bankId } = useParams<{ bankId: string }>();
  const [scenarios, setScenarios] = useState<ExamScenario[]>([]);
  const [questions, setQuestions] = useState<ExamQuestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [publishState, setPublishState] = useState<"idle" | "publishing" | "done" | "error">("idle");

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
    } catch (e) {
      setError(String(e));
      setPublishState("error");
    }
  }

  if (loading) return <p className="p-8 text-sm text-gray-500">Loading…</p>;
  if (error) return <p className="p-8 text-sm text-red-600">{error}</p>;

  const allValidated = questions.every((q) => q.validated);

  return (
    <main className="max-w-3xl mx-auto p-8 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Review &amp; Edit Board</h1>
        <button
          disabled={publishState !== "idle" || allValidated}
          onClick={handleValidateAll}
          className="rounded bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50">
          {publishState === "publishing" ? "Publishing…" :
           publishState === "done" ? "✓ Published" :
           allValidated ? "✓ All validated" : "Validate All & Publish"}
        </button>
      </div>

      {scenarios.map((scenario) => (
        <ScenarioCard
          key={scenario.id}
          bankId={bankId}
          scenario={scenario}
          questions={questionsByScenario(scenario.id)}
          onQuestionUpdate={(updated) =>
            setQuestions((qs) => qs.map((q) => q.id === updated.id ? updated : q))}
        />
      ))}

      {scenarios.length === 0 && (
        <p className="text-sm text-gray-400 text-center py-12">No scenarios generated yet.</p>
      )}
    </main>
  );
}

function ScenarioCard({ bankId, scenario, questions, onQuestionUpdate }: {
  bankId: string;
  scenario: ExamScenario;
  questions: ExamQuestion[];
  onQuestionUpdate: (q: ExamQuestion) => void;
}) {
  const [title, setTitle] = useState(scenario.title);
  const [saving, setSaving] = useState(false);

  const saveTitle = useDebounce(
    useCallback(async (val: string) => {
      setSaving(true);
      try { await patchScenario(bankId, scenario.id, { title: val }); }
      catch { /* silent */ }
      finally { setSaving(false); }
    }, [bankId, scenario.id]),
    600,
  );

  function handleTitleChange(val: string) {
    setTitle(val);
    saveTitle(val);
  }

  return (
    <div className="rounded-lg border bg-white shadow-sm">
      <div className="flex items-center gap-3 border-b px-4 py-3">
        <input
          className="flex-1 rounded border border-transparent bg-transparent px-2 py-1 text-sm font-semibold hover:border-gray-200 focus:border-blue-400 focus:outline-none"
          value={title}
          onChange={(e) => handleTitleChange(e.target.value)} />
        {saving && <span className="text-xs text-gray-400">Saving…</span>}
      </div>
      <div className="divide-y">
        {questions.map((q) => (
          <QuestionCard key={q.id} bankId={bankId} question={q} onUpdate={onQuestionUpdate} />
        ))}
      </div>
      {questions.length === 0 && (
        <p className="py-4 text-center text-xs text-gray-400">No questions</p>
      )}
    </div>
  );
}

function QuestionCard({ bankId, question, onUpdate }: {
  bankId: string;
  question: ExamQuestion;
  onUpdate: (q: ExamQuestion) => void;
}) {
  const [description, setDescription] = useState(question.description);
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);

  const saveDescription = useDebounce(
    useCallback(async (val: string) => {
      setSaving(true);
      try {
        const updated = await patchQuestion(question.id, bankId, { description: val });
        onUpdate(updated);
      } catch { /* silent */ }
      finally { setSaving(false); }
    }, [question.id, bankId, onUpdate]),
    600,
  );

  async function handleValidate() {
    setValidating(true);
    try {
      const updated = await validateQuestion(question.id, bankId);
      onUpdate(updated);
    } catch { /* silent */ }
    finally { setValidating(false); }
  }

  return (
    <div className="px-4 py-3 space-y-2">
      <div className="flex items-start gap-3">
        <span className={`mt-0.5 rounded px-1.5 py-0.5 text-xs font-medium
          ${question.question_type === "mcq" ? "bg-blue-100 text-blue-700" : "bg-purple-100 text-purple-700"}`}>
          {question.question_type.toUpperCase()}
        </span>
        <textarea
          rows={2}
          className="flex-1 rounded border border-transparent bg-transparent px-1 text-sm hover:border-gray-200 focus:border-blue-400 focus:outline-none resize-none"
          value={description}
          onChange={(e) => { setDescription(e.target.value); saveDescription(e.target.value); }} />
        <div className="flex flex-col items-end gap-1">
          {saving && <span className="text-xs text-gray-400">Saving…</span>}
          {question.validated ? (
            <span className="rounded bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">✓ Validated</span>
          ) : (
            <button onClick={handleValidate} disabled={validating}
              className="rounded border border-green-300 px-2 py-0.5 text-xs text-green-600 hover:bg-green-50 disabled:opacity-50">
              {validating ? "…" : "Validate"}
            </button>
          )}
        </div>
      </div>
      {question.question_type === "mcq" && question.options && (
        <ul className="ml-12 space-y-1">
          {question.options.map((opt, i) => (
            <li key={i} className={`flex items-center gap-2 text-xs
              ${(question.correct_answer_indices ?? []).includes(i) ? "text-green-700 font-medium" : "text-gray-500"}`}>
              <span className="font-mono">{opt.label}.</span> {opt.text}
              {(question.correct_answer_indices ?? []).includes(i) && <span className="text-green-500">✓</span>}
            </li>
          ))}
        </ul>
      )}
      {question.question_type === "dissertation" && question.rubric && (
        <div className="ml-12">
          <p className="text-xs text-gray-400 mb-1">Rubric:</p>
          <ul className="space-y-0.5">
            {question.rubric.map((r, i) => (
              <li key={i} className="text-xs text-gray-600">
                <span className="font-medium">{r.criterion}</span> ({r.max_points} pts) — {r.description}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
