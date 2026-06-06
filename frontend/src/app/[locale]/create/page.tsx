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
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { cn } from "@/lib/utils";
import {
  Plus,
  FileText,
  AlertCircle,
  Sparkles,
  CheckCircle,
  X,
} from "lucide-react";

type Step = 0 | 1 | 2 | 3;

const STEP_LABELS = ["Info examen", "Sources", "Scénarios", "Générer"];

const SOURCE_STATUS_VARIANT: Record<
  ExamSource["extraction_status"],
  "warning" | "info" | "success" | "destructive"
> = {
  pending: "warning",
  extracting: "info",
  done: "success",
  failed: "destructive",
};

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

  const go = (s: Step) => {
    setError(null);
    setStep(s);
  };

  // ── Step 0 → create bank ──────────────────────────────────────────────────
  async function handleCreateBank() {
    if (!titleFr.trim()) {
      setError("Le titre est requis");
      return;
    }
    setLoading(true);
    try {
      const bank = await createExamBank({
        title_fr: titleFr,
        subject,
        language,
        passing_score: passingScore,
      });
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
  function updateScenario(
    i: number,
    field: keyof ScenarioBrief,
    value: string | number
  ) {
    setScenarios((s) =>
      s.map((sc, idx) => (idx === i ? { ...sc, [field]: value } : sc))
    );
  }

  // ── Step 3 → generate ────────────────────────────────────────────────────
  const pollStatus = useCallback(
    async (bId: string) => {
      let attempt = 0;
      const max = 40; // 40 × 5s = 200s
      setPolling(true);
      setGenStatus("Mise en file d'attente de la génération…");
      while (attempt < max) {
        await new Promise((r) => setTimeout(r, 5000));
        attempt++;
        try {
          const s = await getGenerationStatus(bId);
          if (s.status === "review") {
            setPolling(false);
            setGenStatus("Terminé ! Redirection vers le tableau de révision…");
            setTimeout(() => router.push(`/${locale}/banks/${bId}/review`), 1500);
            return;
          }
          if (s.status === "draft" && s.error_message) {
            setGenError(s.error_message);
            setPolling(false);
            return;
          }
          setGenStatus(`Génération… (${s.progress_pct ?? 0}%)`);
        } catch {
          /* transient network */
        }
      }
      setPolling(false);
      setGenError("Délai dépassé après 200 s — vérifiez les journaux.");
    },
    [router, locale]
  );

  async function handleGenerate() {
    if (!bankId) return;
    const filled = scenarios.filter((s) => s.title.trim());
    if (!filled.length) {
      setError("Ajoutez au moins un scénario");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await triggerGeneration(bankId, {
        test_objective: objective,
        scenarios_brief: filled,
      });
      go(3);
      pollStatus(bankId);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  // ── UI ────────────────────────────────────────────────────────────────────
  const progressValue = (step / (STEP_LABELS.length - 1)) * 100;

  return (
    <main className="max-w-2xl mx-auto px-4 py-8">
      {/* Step progress */}
      <div className="mb-8 space-y-3">
        <Progress value={progressValue} />
        <div className="flex justify-between">
          {STEP_LABELS.map((label, i) => (
            <div key={i} className="flex flex-col items-center gap-1">
              <div
                className={cn(
                  "flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold border-2 transition-colors",
                  i < step
                    ? "bg-primary border-primary text-primary-foreground"
                    : i === step
                    ? "bg-primary border-primary text-primary-foreground"
                    : "bg-background border-border text-muted-foreground"
                )}
              >
                {i < step ? <CheckCircle className="h-4 w-4" /> : i + 1}
              </div>
              <span
                className={cn(
                  "hidden sm:block text-xs",
                  i === step
                    ? "font-semibold text-foreground"
                    : "text-muted-foreground"
                )}
              >
                {label}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Global error */}
      {error && (
        <Alert variant="destructive" className="mb-5">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Erreur</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* ── Step 0: Exam Info ── */}
      {step === 0 && (
        <div className="space-y-5">
          <h2 className="text-xl font-semibold">Info examen</h2>

          <div className="space-y-1.5">
            <Label htmlFor="title-fr">Titre (FR) *</Label>
            <Input
              id="title-fr"
              value={titleFr}
              onChange={(e) => setTitleFr(e.target.value)}
              placeholder="e.g. Examen de médecine"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="subject">Matière</Label>
            <Input
              id="subject"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="e.g. Pharmacologie"
            />
          </div>

          <div className="flex gap-4">
            <div className="flex-1 space-y-1.5">
              <Label htmlFor="language">Langue</Label>
              <select
                id="language"
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                className="flex h-9 w-full rounded-lg border border-input bg-background px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
              >
                <option value="fr">Français</option>
                <option value="en">English</option>
              </select>
            </div>
            <div className="flex-1 space-y-1.5">
              <Label htmlFor="passing-score">Note de passage (%)</Label>
              <Input
                id="passing-score"
                type="number"
                min={0}
                max={100}
                value={passingScore}
                onChange={(e) => setPassingScore(Number(e.target.value))}
              />
            </div>
          </div>

          <Button
            className="w-full"
            disabled={loading}
            onClick={handleCreateBank}
          >
            {loading ? (
              <>
                <LoadingSpinner size="sm" />
                Création…
              </>
            ) : (
              "Suivant : Téléverser les sources →"
            )}
          </Button>
        </div>
      )}

      {/* ── Step 1: Sources ── */}
      {step === 1 && (
        <div className="space-y-5">
          <h2 className="text-xl font-semibold">Téléverser les documents sources</h2>
          <p className="text-sm text-muted-foreground">
            Téléversez des fichiers PDF ou Word utilisés comme documents de référence pour l&apos;examen.
          </p>

          {/* Upload zone */}
          <label className="flex cursor-pointer flex-col items-center gap-3 rounded-xl border-2 border-dashed border-border p-8 text-center transition-colors hover:border-primary/50 hover:bg-muted/30">
            <FileText className="h-8 w-8 text-muted-foreground" />
            <div>
              <p className="text-sm font-medium">
                {uploadingFile ? "Téléversement…" : "Cliquez pour téléverser un PDF ou Word"}
              </p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                .pdf, .doc, .docx
              </p>
            </div>
            <input
              type="file"
              accept=".pdf,.doc,.docx"
              className="hidden"
              disabled={uploadingFile}
              onChange={handleUploadFile}
            />
          </label>

          {/* Source list */}
          {sources.length > 0 && (
            <div className="space-y-2">
              {sources.map((s) => (
                <Card key={s.id}>
                  <CardContent className="flex items-center gap-3 py-3 px-4">
                    <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <span className="flex-1 truncate text-sm">{s.filename}</span>
                    <Badge variant={SOURCE_STATUS_VARIANT[s.extraction_status]}>
                      {s.extraction_status}
                    </Badge>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          <div className="flex gap-3">
            <Button variant="outline" className="flex-1" onClick={() => go(0)}>
              ← Retour
            </Button>
            <Button className="flex-1" onClick={() => go(2)}>
              Suivant : Scénarios →
            </Button>
          </div>
        </div>
      )}

      {/* ── Step 2: Scenarios ── */}
      {step === 2 && (
        <div className="space-y-5">
          <h2 className="text-xl font-semibold">Configurer les scénarios</h2>

          <div className="space-y-1.5">
            <Label htmlFor="test-objective">Objectif du test *</Label>
            <Textarea
              id="test-objective"
              rows={2}
              value={objective}
              onChange={(e) => setObjective(e.target.value)}
              placeholder="ex. Évaluer la compréhension de la gestion des maladies infectieuses"
            />
          </div>

          {/* Scenario cards */}
          <div className="space-y-3">
            {scenarios.map((sc, i) => (
              <Card key={i}>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm">Scénario {i + 1}</CardTitle>
                    {scenarios.length > 1 && (
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => removeScenario(i)}
                        className="text-muted-foreground hover:text-destructive"
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                </CardHeader>
                <CardContent className="space-y-3 pt-1">
                  <div className="space-y-1.5">
                    <Label htmlFor={`sc-title-${i}`}>Titre</Label>
                    <Input
                      id={`sc-title-${i}`}
                      placeholder="Titre du scénario"
                      value={sc.title}
                      onChange={(e) => updateScenario(i, "title", e.target.value)}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor={`sc-obj-${i}`}>Objectif (facultatif)</Label>
                    <Input
                      id={`sc-obj-${i}`}
                      placeholder="Objectif"
                      value={sc.objective}
                      onChange={(e) =>
                        updateScenario(i, "objective", e.target.value)
                      }
                    />
                  </div>
                  <div className="flex items-center gap-3">
                    <Label htmlFor={`sc-count-${i}`} className="text-xs shrink-0">
                      Questions :
                    </Label>
                    <Input
                      id={`sc-count-${i}`}
                      type="number"
                      min={1}
                      max={20}
                      className="w-20"
                      value={sc.question_count}
                      onChange={(e) =>
                        updateScenario(i, "question_count", Number(e.target.value))
                      }
                    />
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Add scenario button */}
          <button
            type="button"
            onClick={addScenario}
            className="flex w-full items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border py-3 text-sm font-medium text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
          >
            <Plus className="h-4 w-4" />
            Ajouter un scénario
          </button>

          <div className="flex gap-3">
            <Button variant="outline" className="flex-1" onClick={() => go(1)}>
              ← Retour
            </Button>
            <Button
              className="flex-1"
              disabled={loading}
              onClick={handleGenerate}
            >
              {loading ? (
                <>
                  <LoadingSpinner size="sm" />
                  Mise en file…
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4" />
                  Générer l&apos;examen
                </>
              )}
            </Button>
          </div>
        </div>
      )}

      {/* ── Step 3: Generation ── */}
      {step === 3 && (
        <div className="flex flex-col items-center gap-6 py-12 text-center">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
            <Sparkles className="h-8 w-8 text-primary" />
          </div>

          <div>
            <h2 className="text-xl font-semibold">Génération de votre examen</h2>
            {genStatus && !genError && (
              <p className="mt-1 text-sm text-muted-foreground">{genStatus}</p>
            )}
          </div>

          {polling && (
            <LoadingSpinner size="lg" className="text-primary" />
          )}

          {!polling && !genError && genStatus?.startsWith("Terminé") && (
            <div className="flex items-center gap-2 text-emerald-600">
              <CheckCircle className="h-5 w-5" />
              <span className="text-sm font-medium">{genStatus}</span>
            </div>
          )}

          {genError && (
            <Alert variant="destructive" className="w-full text-left">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>Échec de la génération</AlertTitle>
              <AlertDescription className="mt-2 flex flex-col gap-2">
                <span>{genError}</span>
                <Button
                  variant="outline"
                  size="sm"
                  className="w-fit border-destructive/40 text-destructive hover:bg-destructive/10"
                  onClick={() => go(2)}
                >
                  ← Retour aux scénarios
                </Button>
              </AlertDescription>
            </Alert>
          )}
        </div>
      )}
    </main>
  );
}
