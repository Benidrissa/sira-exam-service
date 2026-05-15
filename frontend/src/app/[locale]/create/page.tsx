"use client";

import { useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  createExamBank,
  uploadExamSource,
  listExamSources,
  triggerGeneration,
  getGenerationStatus,
} from "@/lib/api";
import type { ExamSource, ScenarioBrief } from "@/types/exam";

type Step = 0 | 1 | 2 | 3;

export default function CreateExamPage() {
  const router = useRouter();
  const params = useParams<{ locale?: string }>();
  const locale = params?.locale ?? "fr";
  const [step, setStep] = useState<Step>(0);
  const [bankId, setBankId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Step 0 state
  const [titleFr, setTitleFr] = useState("");
  const [subject, setSubject] = useState("");
  const [language, setLanguage] = useState("fr");
  const [passingScore, setPassingScore] = useState(80);

  // Step 1 state
  const [sources, setSources] = useState<ExamSource[]>([]);
  const [uploadingFile, setUploadingFile] = useState(false);

  // Step 2 state
  const [scenarios, setScenarios] = useState<ScenarioBrief[]>([
    { title: "", objective: "", question_count: 3 },
  ]);
  const [objective, setObjective] = useState("");

  // Step 3 state
  const [genStatus, setGenStatus] = useState<string | null>(null);
  const [genError, setGenError] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);

  const go = (s: Step) => { setError(null); setStep(s); };

  // ── Step 0 → create bank ──────────────────────────────────────────────────
  async function handleCreateBank() {
    if (!titleFr.trim()) { setError("Title is required"); return; }
    setLoading(true);
    try {
      const bank = await createExamBank({ title_fr: titleFr, subject, language, passing_score: passingScore });
      setBankId(bank.id);
      go(1);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  // ── Step 1 → upload sources ───────────────────────────────────────────────
  async function handleUploadFile(e: React.ChangeEvent<HTMLInputElement>) {
    if (!bankId || !e.target.files?.[0]) return;
    setUploadingFile(true);
    setError(null);
    try {
      await uploadExamSource(bankId, e.target.files[0]);
      const updated = await listExamSources(bankId);
      setSources(updated);
    } catch (err) {
      setError(String(err));
    } finally {
      setUploadingFile(false);
      e.target.value = "";
    }
  }

  // ── Step 2 → configure scenarios ─────────────────────────────────────────
  function addScenario() {
    setScenarios((s) => [...s, { title: "", objective: "", question_count: 3 }]);
  }
  function removeScenario(i: number) {
    setScenarios((s) => s.filter((_, idx) => idx !== i));
  }
  function updateScenario(i: number, field: keyof ScenarioBrief, value: string | number) {
    setScenarios((s) => s.map((sc, idx) => idx === i ? { ...sc, [field]: value } : sc));
  }

  // ── Step 3 → generate ────────────────────────────────────────────────────
  const pollStatus = useCallback(async (bId: string) => {
    let attempt = 0;
    const max = 40; // 40 × 5s = 200s
    setPolling(true);
    setGenStatus("Enqueueing generation…");
    while (attempt < max) {
      await new Promise((r) => setTimeout(r, 5000));
      attempt++;
      try {
        const s = await getGenerationStatus(bId);
        if (s.status === "review") {
          setPolling(false);
          setGenStatus("Done! Redirecting to review board…");
          setTimeout(() => router.push(`/${locale}/banks/${bId}/review`), 1500);
          return;
        }
        if (s.status === "draft" && s.error_message) {
          setGenError(s.error_message);
          setPolling(false);
          return;
        }
        setGenStatus(`Generating… (${s.progress_pct ?? 0}%)`);
      } catch { /* transient network */ }
    }
    setPolling(false);
    setGenError("Timed out after 200 s — check logs.");
  }, [router]);

  async function handleGenerate() {
    if (!bankId) return;
    const filled = scenarios.filter((s) => s.title.trim());
    if (!filled.length) { setError("Add at least one scenario"); return; }
    setLoading(true);
    setError(null);
    try {
      await triggerGeneration(bankId, { test_objective: objective, scenarios_brief: filled });
      go(3);
      pollStatus(bankId);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  // ── UI ────────────────────────────────────────────────────────────────────
  const steps = ["Exam Info", "Sources", "Scenarios", "Generate"];

  return (
    <main className="max-w-2xl mx-auto p-8">
      {/* Progress bar */}
      <div className="flex items-center gap-2 mb-8">
        {steps.map((label, i) => (
          <div key={i} className="flex items-center gap-2 flex-1 last:flex-none">
            <div className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold
              ${i <= step ? "bg-blue-600 text-white" : "bg-gray-200 text-gray-500"}`}>
              {i + 1}
            </div>
            <span className={`hidden sm:inline text-sm ${i === step ? "font-medium" : "text-gray-400"}`}>
              {label}
            </span>
            {i < steps.length - 1 && <div className={`flex-1 h-0.5 ${i < step ? "bg-blue-600" : "bg-gray-200"}`} />}
          </div>
        ))}
      </div>

      {error && <div className="mb-4 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700">{error}</div>}

      {/* Step 0: Exam Info */}
      {step === 0 && (
        <div className="space-y-4">
          <h2 className="text-xl font-semibold">Exam Info</h2>
          <label className="block">
            <span className="text-sm font-medium">Title (FR) *</span>
            <input className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={titleFr} onChange={(e) => setTitleFr(e.target.value)} placeholder="e.g. Examen de médecine" />
          </label>
          <label className="block">
            <span className="text-sm font-medium">Subject</span>
            <input className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="e.g. Pharmacologie" />
          </label>
          <div className="flex gap-4">
            <label className="flex-1 block">
              <span className="text-sm font-medium">Language</span>
              <select className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm"
                value={language} onChange={(e) => setLanguage(e.target.value)}>
                <option value="fr">Français</option>
                <option value="en">English</option>
              </select>
            </label>
            <label className="flex-1 block">
              <span className="text-sm font-medium">Passing score (%)</span>
              <input type="number" min={0} max={100}
                className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm"
                value={passingScore} onChange={(e) => setPassingScore(Number(e.target.value))} />
            </label>
          </div>
          <button disabled={loading}
            onClick={handleCreateBank}
            className="w-full rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
            {loading ? "Creating…" : "Next: Upload Sources →"}
          </button>
        </div>
      )}

      {/* Step 1: Sources */}
      {step === 1 && (
        <div className="space-y-4">
          <h2 className="text-xl font-semibold">Upload Source Documents</h2>
          <p className="text-sm text-gray-500">Upload PDF or Word files used as exam reference material.</p>
          <label className="flex cursor-pointer items-center gap-2 rounded border-2 border-dashed border-gray-300 p-4 hover:border-blue-400">
            <span className="text-sm text-gray-600">{uploadingFile ? "Uploading…" : "Click to upload PDF / Word"}</span>
            <input type="file" accept=".pdf,.doc,.docx" className="hidden"
              disabled={uploadingFile} onChange={handleUploadFile} />
          </label>
          {sources.length > 0 && (
            <ul className="space-y-2">
              {sources.map((s) => (
                <li key={s.id} className="flex items-center gap-3 rounded border bg-gray-50 px-3 py-2 text-sm">
                  <span className="flex-1 truncate">{s.filename}</span>
                  <span className={`rounded px-2 py-0.5 text-xs font-medium
                    ${s.extraction_status === "done" ? "bg-green-100 text-green-700" :
                      s.extraction_status === "failed" ? "bg-red-100 text-red-700" :
                      "bg-yellow-100 text-yellow-700"}`}>
                    {s.extraction_status}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <div className="flex gap-3">
            <button onClick={() => go(0)} className="flex-1 rounded border px-4 py-2 text-sm hover:bg-gray-50">← Back</button>
            <button onClick={() => go(2)} className="flex-1 rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
              Next: Scenarios →
            </button>
          </div>
        </div>
      )}

      {/* Step 2: Scenarios */}
      {step === 2 && (
        <div className="space-y-4">
          <h2 className="text-xl font-semibold">Configure Scenarios</h2>
          <label className="block">
            <span className="text-sm font-medium">Test Objective *</span>
            <textarea rows={2}
              className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={objective} onChange={(e) => setObjective(e.target.value)}
              placeholder="e.g. Assess understanding of infectious disease management" />
          </label>
          {scenarios.map((sc, i) => (
            <div key={i} className="rounded border bg-gray-50 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">Scenario {i + 1}</span>
                {scenarios.length > 1 && (
                  <button onClick={() => removeScenario(i)} className="text-xs text-red-500 hover:underline">Remove</button>
                )}
              </div>
              <input className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
                placeholder="Scenario title" value={sc.title}
                onChange={(e) => updateScenario(i, "title", e.target.value)} />
              <input className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
                placeholder="Objective (optional)" value={sc.objective}
                onChange={(e) => updateScenario(i, "objective", e.target.value)} />
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500">Questions:</span>
                <input type="number" min={1} max={20}
                  className="w-20 rounded border border-gray-300 px-2 py-1 text-sm"
                  value={sc.question_count}
                  onChange={(e) => updateScenario(i, "question_count", Number(e.target.value))} />
              </div>
            </div>
          ))}
          <button onClick={addScenario} className="w-full rounded border-2 border-dashed border-gray-300 py-2 text-sm text-gray-500 hover:border-blue-400">
            + Add Scenario
          </button>
          <div className="flex gap-3">
            <button onClick={() => go(1)} className="flex-1 rounded border px-4 py-2 text-sm hover:bg-gray-50">← Back</button>
            <button disabled={loading} onClick={handleGenerate}
              className="flex-1 rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
              {loading ? "Enqueuing…" : "Generate Exam →"}
            </button>
          </div>
        </div>
      )}

      {/* Step 3: Polling */}
      {step === 3 && (
        <div className="space-y-4 text-center">
          <h2 className="text-xl font-semibold">Generating Your Exam</h2>
          {polling && (
            <div className="flex flex-col items-center gap-3">
              <div className="h-10 w-10 animate-spin rounded-full border-4 border-blue-200 border-t-blue-600" />
              <p className="text-sm text-gray-600">{genStatus}</p>
            </div>
          )}
          {!polling && !genError && <p className="text-sm text-green-600">{genStatus}</p>}
          {genError && (
            <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700">
              Generation failed: {genError}
              <button className="ml-2 underline" onClick={() => go(2)}>← Back</button>
            </div>
          )}
        </div>
      )}
    </main>
  );
}
