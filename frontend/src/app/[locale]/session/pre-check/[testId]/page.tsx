"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  startAttempt,
  startProctoringSession,
  getReferenceFrameUploadUrl,
  recordReferenceFrame,
  giveConsent,
} from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface SystemCheck {
  label: string;
  passed: boolean | null;
  warning?: string; // non-blocking warning text
}

// ---------------------------------------------------------------------------
// Pre-check wizard
// ---------------------------------------------------------------------------
export default function PreCheckPage() {
  const { testId } = useParams<{ testId: string }>();
  const router = useRouter();

  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [initError, setInitError] = useState<string | null>(null);

  // AI tier: 0=server-only, 1=YOLO+MediaPipe, 2=SmolVLM
  const [aiTier, setAiTier] = useState<0 | 1 | 2>(0);
  // null=not started, 0-100=loading, 101=done, -1=failed
  const [modelLoadProgress, setModelLoadProgress] = useState<number | null>(null);

  // Initialise attempt + proctoring session on page load
  useEffect(() => {
    (async () => {
      try {
        const attempt = await startAttempt(testId);
        const ps = await startProctoringSession(attempt.attempt_id);
        setSessionId(ps.session_id);
      } catch (e) {
        setInitError(String(e));
      }
    })();
  }, [testId]);

  // Step 1: hardware detection + model prefetch
  useEffect(() => {
    if (step !== 1) return;

    // Detect WebGPU for Tier 2
    const detectTier = async () => {
      try {
        const gpu = (navigator as Navigator & { gpu?: { requestAdapter(): Promise<unknown> } }).gpu;
        const deviceMem = (navigator as Navigator & { deviceMemory?: number }).deviceMemory ?? 0;
        if (gpu && deviceMem >= 8) {
          const adapter = await gpu.requestAdapter();
          if (adapter) {
            setAiTier(2);
            return;
          }
        }
        if (deviceMem === 0 || deviceMem >= 4) setAiTier(1);
        // else aiTier stays 0
      } catch {
        setAiTier(1);
      }
    };
    void detectTier();

    // Check extended display
    const screenExt = (window.screen as Screen & { isExtended?: boolean }).isExtended;
    if (screenExt === true) {
      console.warn("Extended display detected during pre-check");
    }

    // Start model download in background
    let cancelled = false;
    const loadModel = async () => {
      setModelLoadProgress(0);
      const timeout = setTimeout(() => {
        if (!cancelled) {
          setModelLoadProgress(-1);
          setAiTier(0);
        }
      }, 60_000);

      try {
        const { getVLMConfig } = await import("@/lib/api");
        const config = await getVLMConfig();

        if (config.tier1_models.length === 0) {
          clearTimeout(timeout);
          if (!cancelled) setModelLoadProgress(-1);
          return;
        }

        // Download first model shard to warm the cache
        const firstModel = config.tier1_models[0];
        if (firstModel?.url) {
          const resp = await fetch(firstModel.url, { method: "GET" });
          if (resp.ok) {
            clearTimeout(timeout);
            if (!cancelled) setModelLoadProgress(101);
            return;
          }
        }
        clearTimeout(timeout);
        if (!cancelled) setModelLoadProgress(101); // config loaded, model URL available
      } catch {
        clearTimeout(timeout);
        if (!cancelled) {
          setModelLoadProgress(-1);
          setAiTier(0);
        }
      }
    };
    void loadModel();

    return () => {
      cancelled = true;
    };
  }, [step]);

  if (initError) {
    return <p className="p-8 text-sm text-red-600">{initError}</p>;
  }

  return (
    <main className="min-h-screen bg-gray-50 flex items-center justify-center p-6">
      <div className="w-full max-w-xl bg-white rounded-2xl shadow-md p-8 space-y-6">
        {/* Step indicator */}
        <StepIndicator current={step} total={4} />

        {step === 1 && (
          <SystemCheckStep
            modelLoadProgress={modelLoadProgress}
            onNext={() => setStep(2)}
          />
        )}
        {step === 2 && (
          <CameraPreviewStep
            sessionId={sessionId}
            onNext={() => setStep(3)}
          />
        )}
        {step === 3 && (
          <IdentityCheckStep onNext={() => setStep(4)} />
        )}
        {step === 4 && (
          <ConsentStep
            sessionId={sessionId}
            testId={testId}
            aiTier={aiTier}
            onStart={() => router.push(`/exams/${testId}/play`)}
          />
        )}
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Step indicator
// ---------------------------------------------------------------------------
function StepIndicator({ current, total }: { current: number; total: number }) {
  return (
    <div className="flex items-center gap-2">
      {Array.from({ length: total }, (_, i) => {
        const n = i + 1;
        const done = n < current;
        const active = n === current;
        return (
          <div key={n} className="flex items-center gap-2">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold
                ${done ? "bg-green-500 text-white" : active ? "bg-blue-600 text-white" : "bg-gray-200 text-gray-500"}`}>
              {done ? "✓" : n}
            </div>
            {i < total - 1 && (
              <div className={`h-0.5 w-8 ${done ? "bg-green-400" : "bg-gray-200"}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 1 — System Check
// ---------------------------------------------------------------------------
function SystemCheckStep({
  modelLoadProgress,
  onNext,
}: {
  modelLoadProgress: number | null;
  onNext: () => void;
}) {
  const [checks, setChecks] = useState<SystemCheck[]>([
    { label: "Camera API available", passed: null },
    { label: "Fullscreen API available", passed: null },
    { label: "Screen resolution ≥ 1280×720", passed: null },
    { label: "RAM (4 GB min)", passed: null },
    { label: "WebGL 2.0", passed: null },
    { label: "AI Proctoring Model", passed: null },
  ]);

  // Extended display warning (checked once on mount)
  const isExtended =
    typeof window !== "undefined"
      ? (window.screen as Screen & { isExtended?: boolean }).isExtended === true
      : false;

  useEffect(() => {
    // Static checks run synchronously
    const deviceMemory = (navigator as Navigator & { deviceMemory?: number }).deviceMemory ?? 0;
    const canvas = document.createElement("canvas");
    const webglCtx = canvas.getContext("webgl2");

    const ramPassed = deviceMemory >= 4 || deviceMemory === 0;
    const ramWarning =
      deviceMemory > 0 && deviceMemory < 4
        ? "Memory below recommended — standard cloud proctoring will be used"
        : undefined;

    const webglPassed = webglCtx !== null;
    const webglWarning = webglCtx === null
      ? "Update your browser (Chrome 56+ required)"
      : undefined;

    const results: boolean[] = [
      typeof navigator.mediaDevices?.getUserMedia === "function",
      typeof document.documentElement.requestFullscreen === "function",
      screen.width >= 1280 && screen.height >= 720,
      ramPassed,
      webglPassed,
    ];

    setChecks((prev) =>
      prev.map((c, i) => {
        if (i < 5) {
          const extra: Partial<SystemCheck> = {};
          if (i === 3) extra.warning = ramWarning;
          if (i === 4) extra.warning = webglWarning;
          return { ...c, passed: results[i] ?? null, ...extra };
        }
        // AI check stays null until modelLoadProgress updates
        return c;
      }),
    );
  }, []);

  // Update AI check row based on modelLoadProgress
  useEffect(() => {
    const aiPassed =
      modelLoadProgress === 101 ? true : modelLoadProgress === -1 ? false : null;
    const aiWarning =
      modelLoadProgress === -1
        ? "AI model unavailable — using secure cloud analysis"
        : undefined;
    setChecks((prev) =>
      prev.map((c, i) =>
        i === 5 ? { ...c, passed: aiPassed, warning: aiWarning } : c,
      ),
    );
  }, [modelLoadProgress]);

  // "Next" is enabled when: first 5 checks pass (or have non-blocking warning), AI check not failed (null or 101)
  const criticalChecks = checks.slice(0, 5);
  const allCriticalPassed = criticalChecks.every(
    (c) => c.passed === true || (c.passed === false && c.warning !== undefined),
  );
  const aiCheck = checks[5];
  const aiBlocking = aiCheck?.passed === false && aiCheck.warning === undefined;
  const canProceed = allCriticalPassed && !aiBlocking;

  const aiLabel = () => {
    if (modelLoadProgress === null) return "AI Proctoring Model";
    if (modelLoadProgress === -1) return "AI Proctoring Model";
    if (modelLoadProgress === 101) return "AI Proctoring Model";
    return `AI Proctoring Model (downloading…)`;
  };

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold">Step 1 — System Check</h2>
      <p className="text-sm text-gray-500">
        Verifying your system meets the requirements for remote proctoring.
      </p>

      {isExtended && (
        <div className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded p-2">
          ⚠ Secondary display detected. Disconnect additional monitors before starting the exam.
        </div>
      )}

      <ul className="space-y-3">
        {checks.map((c, i) => {
          const label = i === 5 ? aiLabel() : c.label;
          const isWarning = c.passed === false && c.warning !== undefined;
          return (
            <li key={c.label} className="flex flex-col gap-0.5">
              <div className="flex items-center gap-3">
                <span className="text-lg">
                  {c.passed === null
                    ? "⏳"
                    : isWarning
                    ? "⚠️"
                    : c.passed
                    ? "✅"
                    : "❌"}
                </span>
                <span
                  className={`text-sm ${
                    c.passed === false && !isWarning
                      ? "text-red-600"
                      : isWarning
                      ? "text-amber-700"
                      : "text-gray-700"
                  }`}>
                  {label}
                </span>
              </div>
              {isWarning && c.warning && (
                <p className="ml-9 text-xs text-amber-600">{c.warning}</p>
              )}
            </li>
          );
        })}
      </ul>

      {!canProceed && criticalChecks.some((c) => c.passed === false && !c.warning) && (
        <div className="rounded-lg bg-yellow-50 border border-yellow-200 p-4 text-sm text-yellow-800 space-y-1">
          <p className="font-semibold">Action required:</p>
          {checks[0]?.passed === false && !checks[0].warning && (
            <p>• Allow camera access in your browser settings.</p>
          )}
          {checks[1]?.passed === false && !checks[1].warning && (
            <p>• Use a modern browser that supports fullscreen (Chrome, Firefox, Edge).</p>
          )}
          {checks[2]?.passed === false && !checks[2].warning && (
            <p>• Use a screen with at least 1280×720 resolution.</p>
          )}
          {checks[3]?.passed === false && !checks[3].warning && (
            <p>• Insufficient RAM detected.</p>
          )}
          {checks[4]?.passed === false && !checks[4].warning && (
            <p>• WebGL 2.0 is required. Update your browser (Chrome 56+).</p>
          )}
        </div>
      )}

      <button
        disabled={!canProceed}
        onClick={onNext}
        className="w-full rounded-lg bg-blue-600 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-40 transition">
        Next
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 2 — Camera Preview + Reference Frame
// ---------------------------------------------------------------------------
function CameraPreviewStep({
  sessionId,
  onNext,
}: {
  sessionId: string | null;
  onNext: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [thumbnail, setThumbnail] = useState<string | null>(null);
  const [capturing, setCapturing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    navigator.mediaDevices
      .getUserMedia({ video: true, audio: false })
      .then((stream) => {
        streamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;
      })
      .catch((e) => setError(String(e)));

    return () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const captureReferenceFrame = useCallback(async () => {
    const video = videoRef.current;
    if (!video || !video.videoWidth || !sessionId) return;
    setCapturing(true);
    setError(null);
    try {
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      canvas.getContext("2d")?.drawImage(video, 0, 0);

      const dataUrl = canvas.toDataURL("image/jpeg", 0.9);
      setThumbnail(dataUrl);

      await new Promise<void>((resolve, reject) => {
        canvas.toBlob(
          async (blob) => {
            if (!blob) { reject(new Error("Canvas toBlob returned null")); return; }
            try {
              const { upload_url } = await getReferenceFrameUploadUrl(sessionId);
              const res = await fetch(upload_url, {
                method: "PUT",
                body: blob,
                headers: { "Content-Type": "image/jpeg" },
              });
              if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
              // Extract storage_key from the upload_url (path after host)
              const storageKey = new URL(upload_url).pathname.slice(1);
              await recordReferenceFrame(sessionId, storageKey);
              resolve();
            } catch (err) {
              reject(err);
            }
          },
          "image/jpeg",
          0.9,
        );
      });
    } catch (e) {
      setError(String(e));
      setThumbnail(null);
    } finally {
      setCapturing(false);
    }
  }, [sessionId]);

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold">Step 2 — Camera Preview</h2>
      <p className="text-sm text-gray-500">
        Make sure your face is clearly visible, then capture your reference photo.
      </p>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="rounded-lg overflow-hidden bg-black aspect-video">
        <video ref={videoRef} autoPlay muted playsInline className="w-full h-full object-cover" />
      </div>

      {thumbnail && (
        <div className="space-y-1">
          <p className="text-xs text-gray-500 font-medium">Captured reference frame:</p>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={thumbnail} alt="Reference frame" className="w-32 h-24 rounded border object-cover" />
        </div>
      )}

      {!thumbnail ? (
        <button
          onClick={captureReferenceFrame}
          disabled={capturing || !sessionId}
          className="w-full rounded-lg bg-gray-800 py-2.5 text-sm font-medium text-white hover:bg-gray-900 disabled:opacity-40 transition">
          {capturing ? "Capturing…" : "Capture reference frame"}
        </button>
      ) : (
        <button
          onClick={onNext}
          className="w-full rounded-lg bg-blue-600 py-2.5 text-sm font-medium text-white hover:bg-blue-700 transition">
          Use this photo
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 3 — Identity Check
// ---------------------------------------------------------------------------
function IdentityCheckStep({ onNext }: { onNext: () => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [thumbnail, setThumbnail] = useState<string | null>(null);
  const [capturing, setCapturing] = useState(false);

  useEffect(() => {
    navigator.mediaDevices
      .getUserMedia({ video: true, audio: false })
      .then((stream) => {
        streamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;
      })
      .catch((e) => console.error("Camera error:", e));

    return () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const captureId = useCallback(() => {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return;
    setCapturing(true);
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    setThumbnail(canvas.toDataURL("image/jpeg", 0.9));
    setCapturing(false);
  }, []);

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold">Step 3 — Identity Check</h2>
      <p className="text-sm text-gray-500">
        Please hold your ID up to the camera and click <strong>Capture</strong>.
      </p>

      <div className="rounded-lg overflow-hidden bg-black aspect-video">
        <video ref={videoRef} autoPlay muted playsInline className="w-full h-full object-cover" />
      </div>

      {thumbnail && (
        <div className="space-y-1">
          <p className="text-xs text-gray-500 font-medium">Captured ID photo:</p>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={thumbnail} alt="ID photo" className="w-32 h-24 rounded border object-cover" />
        </div>
      )}

      {!thumbnail ? (
        <button
          onClick={captureId}
          disabled={capturing}
          className="w-full rounded-lg bg-gray-800 py-2.5 text-sm font-medium text-white hover:bg-gray-900 disabled:opacity-40 transition">
          {capturing ? "Capturing…" : "Capture"}
        </button>
      ) : (
        <button
          onClick={onNext}
          className="w-full rounded-lg bg-blue-600 py-2.5 text-sm font-medium text-white hover:bg-blue-700 transition">
          Continue
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 4 — Consent
// ---------------------------------------------------------------------------
function ConsentStep({
  sessionId,
  testId,
  aiTier,
  onStart,
}: {
  sessionId: string | null;
  testId: string;
  aiTier: 0 | 1 | 2;
  onStart: () => void;
}) {
  const [consented, setConsented] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleStartExam = async () => {
    if (!consented || !sessionId) return;
    setLoading(true);
    setError(null);
    try {
      await giveConsent(sessionId);

      // Store AI tier so the exam play page can configure proctoring
      sessionStorage.setItem("proctor_ai_tier", String(aiTier));

      // Request fullscreen from user gesture (Step 4 button click)
      try {
        await document.documentElement.requestFullscreen();
      } catch {
        // Fullscreen denied — exam page will show the fullscreen gate
      }

      onStart();
    } catch (e) {
      setError(String(e));
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold">Step 4 — Consent</h2>
      <p className="text-sm text-gray-700">
        By starting this exam, you consent to webcam monitoring throughout the session. Your video
        feed will be used solely to ensure exam integrity.
      </p>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <label className="flex items-start gap-3 cursor-pointer">
        <input
          type="checkbox"
          checked={consented}
          onChange={(e) => setConsented(e.target.checked)}
          className="mt-0.5 accent-blue-600 w-4 h-4"
        />
        <span className="text-sm text-gray-700">
          I understand and consent to video proctoring for exam{" "}
          <strong>{testId}</strong>.
        </span>
      </label>

      <button
        disabled={!consented || loading || !sessionId}
        onClick={() => void handleStartExam()}
        className="w-full rounded-lg bg-green-600 py-2.5 text-sm font-semibold text-white hover:bg-green-700 disabled:opacity-40 transition">
        {loading ? "Starting…" : "Start Exam"}
      </button>
    </div>
  );
}
