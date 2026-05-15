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
      // Fetch or create a test and show the student link
      try {
        const API = process.env.NEXT_PUBLIC_EXAM_API_URL ?? "http://localhost:8001/api/v1";
        let tests = await (await fetch(`${API}/exam/banks/${bankId}/tests`, { credentials: "include" })).json();
        if (!tests.length) {
          // Auto-create a test
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

  if (loading) return (
    <main className="max-w-3xl mx-auto p-8">
      <div className="space-y-4">
        {[1,2,3].map(i => <div key={i} className="h-32 animate-pulse rounded-xl bg-gray-100" />)}
      </div>
    </main>
  );
  if (error) return (
    <main className="max-w-3xl mx-auto p-8">
      <div className="rounded-xl border border-red-200 bg-red-50 p-6">
        <p className="font-medium text-red-700">Failed to load</p>
        <p className="mt-1 text-sm text-red-500">{error}</p>
        <button onClick={() => router.back()} className="mt-3 text-sm text-red-600 underline">Go back</button>
      </div>
    </main>
  );

  const allValidated = questions.length > 0 && questions.every((q) => q.validated);

  return (
    <main className="max-w-3xl mx-auto p-6 pb-12 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Review &amp; Edit</h1>
          <p className="text-xs text-gray-400 mt-0.5">{questions.length} questions · {scenarios.length} scenarios</p>
        </div>
        <div className="flex items-center gap-2">
          {saveError && <span className="text-xs text-red-500">{saveError}</span>}
          {publishState === "done" ? (
            <span className="rounded-lg bg-green-50 border border-green-200 px-3 py-1.5 text-sm font-medium text-green-700">✓ Published</span>
          ) : (
            <button
              disabled={publishState === "publishing" || questions.length === 0}
              onClick={handleValidateAll}
              className="rounded-lg bg-green-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-green-700 disabled:opacity-50 transition-colors">
              {publishState === "publishing" ? "Publishing…" : allValidated ? "Publish Bank" : "Validate All & Publish"}
            </button>
          )}
        </div>
      </div>

      {/* Test link shown after publish */}
      {testLink && (
        <div className="rounded-xl border border-blue-200 bg-blue-50 p-4">
          <p className="text-sm font-semibold text-blue-800 mb-2">✓ Bank published! Share this link with students:</p>
          <div className="flex items-center gap-2">
            <code className="flex-1 rounded bg-white border border-blue-200 px-3 py-1.5 text-xs text-blue-700 truncate">{testLink}</code>
            <button
              onClick={async () => { await navigator.clipboard.writeText(testLink); }}
              className="shrink-0 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700"
            >
              Copy
            </button>
          </div>
        </div>
      )}

      {questions.length === 0 && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700">
          No questions generated yet. Go back and trigger generation first.
        </div>
      )}


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
        <p className="text-sm text-gray-400 text-center py-12">No scenarios generated yet.</p>
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
          <QuestionCard key={q.id} bankId={bankId} question={q} onUpdate={onQuestionUpdate} onSaveError={onSaveError} />
        ))}
      </div>
      {questions.length === 0 && (
        <p className="py-4 text-center text-xs text-gray-400">No questions</p>
      )}
    </div>
  );
}

function QuestionCard({ bankId, question, onUpdate, onSaveError }: {
  bankId: string;
  question: ExamQuestion;
  onUpdate: (q: ExamQuestion) => void;
  onSaveError: (msg: string) => void;
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
