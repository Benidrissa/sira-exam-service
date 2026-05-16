/// <reference lib="webworker" />
/**
 * EdgeProctorWorker — Tier-1 on-device proctoring (E3-12)
 * MediaPipe FaceLandmarker + ONNX YOLO-World-S INT8 (YOLO stubbed, face detection live)
 *
 * Message protocol:
 *   IN:  { type: "init", mediapipeWasmUrl, taskModelUrl, onnxModelUrl, modelVersion }
 *   IN:  { type: "infer", frame: ImageBitmap, snapshotId: string }
 *   OUT: { type: "ready" }
 *   OUT: { type: "unsupported", reason: string }
 *   OUT: { type: "result", snapshotId, verdict, violationType, confidence, inferenceMs, modelVersion }
 *   OUT: { type: "error", snapshotId, message }
 */

import * as ort from "onnxruntime-web";
import { FaceLandmarker, FilesetResolver } from "@mediapipe/tasks-vision";

// ── Types ─────────────────────────────────────────────────────────────────────

type Verdict = "clean" | "flagged" | "uncertain" | "error";

type ViolationType =
  | "none"
  | "no_face"
  | "multiple_people"
  | "looking_away"
  | "phone_detected"
  | "another_screen";

interface FrameResult {
  snapshotId: string;
  verdict: Verdict;
  violationType: ViolationType;
  confidence: number;
  inferenceMs: number;
  modelVersion: string;
}

interface PendingFrame {
  bitmap: ImageBitmap;
  snapshotId: string;
}

// ── Worker state ──────────────────────────────────────────────────────────────

let faceLandmarker: FaceLandmarker | null = null;
let onnxSession: ort.InferenceSession | null = null;
let currentModelVersion = "v0.0.0";
let busy = false;
let pendingFrame: PendingFrame | null = null;

// ── WASM SIMD probe ───────────────────────────────────────────────────────────

async function checkSimdSupport(): Promise<boolean> {
  const simdBytes = new Uint8Array([
    0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00, 0x01, 0x04, 0x01, 0x60,
    0x00, 0x00, 0x03, 0x02, 0x01, 0x00, 0x0a, 0x09, 0x01, 0x07, 0x00, 0xfd,
    0x0f, 0x00, 0x00, 0x00, 0x00, 0x0b,
  ]);
  return WebAssembly.validate(simdBytes);
}

// ── Model loading ─────────────────────────────────────────────────────────────

async function loadModels(
  mediapipeWasmUrl: string,
  taskModelUrl: string,
  onnxModelUrl: string,
): Promise<void> {
  // 1. MediaPipe FaceLandmarker (fully functional)
  const vision = await FilesetResolver.forVisionTasks(mediapipeWasmUrl);
  faceLandmarker = await FaceLandmarker.createFromOptions(vision, {
    baseOptions: {
      modelAssetPath: taskModelUrl,
      delegate: "CPU", // GPU not available in workers
    },
    numFaces: 3,
    runningMode: "VIDEO",
    outputFaceBlendshapes: false,
    outputFacialTransformationMatrixes: true,
  });

  // 2. ONNX session (only if URL is provided; skip if empty)
  if (onnxModelUrl) {
    ort.env.wasm.numThreads = 1;
    try {
      onnxSession = await ort.InferenceSession.create(onnxModelUrl, {
        executionProviders: ["wasm"],
      });
    } catch {
      // Non-fatal — face detection still works without YOLO
      onnxSession = null;
    }
  }

  self.postMessage({ type: "ready" });
}

// ── Gaze yaw from transformation matrix ──────────────────────────────────────

function computeGazeYawDeg(matrix: number[]): number {
  // Column-major 4x4: matrix[8] = row2,col0 = sin(yaw)
  const sinYaw = Math.max(-1, Math.min(1, matrix[8] ?? 0));
  return (Math.asin(sinYaw) * 180) / Math.PI;
}

// ── YOLO inference (stub — replace in E3-13) ──────────────────────────────────

interface YoloDetection {
  className: string;
  score: number;
}

// Returns empty array until E3-13 replaces this with real inference
async function runYolo(_bitmap: ImageBitmap): Promise<YoloDetection[]> {
  // TODO(E3-13): implement real ONNX inference
  // Input: resize to 640x640, normalize Float32 CHW, shape [1,3,640,640]
  // Output 'output0': shape [1, num_classes+4, 8400] in YOLOv8 format
  if (!onnxSession) return [];
  return [];
}

// ── Verdict computation ───────────────────────────────────────────────────────

type FaceDetectResult = ReturnType<FaceLandmarker["detectForVideo"]>;

function computeVerdict(
  faceResults: FaceDetectResult,
  yoloDetections: YoloDetection[],
): Pick<FrameResult, "verdict" | "violationType" | "confidence"> {
  const faceCount = faceResults.faceLandmarks.length;

  if (faceCount === 0) {
    return { verdict: "flagged", violationType: "no_face", confidence: 0.95 };
  }
  if (faceCount >= 2) {
    return { verdict: "flagged", violationType: "multiple_people", confidence: 0.88 };
  }

  // Gaze yaw check using transformation matrix
  const matrices = faceResults.facialTransformationMatrixes;
  if (matrices && matrices.length > 0 && matrices[0]) {
    const yaw = computeGazeYawDeg(matrices[0].data);
    if (Math.abs(yaw) > 35) {
      return { verdict: "flagged", violationType: "looking_away", confidence: 0.82 };
    }
  }

  const phone = yoloDetections.find((d) => d.className === "cell_phone" && d.score >= 0.7);
  if (phone) {
    return { verdict: "flagged", violationType: "phone_detected", confidence: phone.score };
  }

  const screen = yoloDetections.find(
    (d) => (d.className === "laptop" || d.className === "monitor") && d.score >= 0.65,
  );
  if (screen) {
    return { verdict: "flagged", violationType: "another_screen", confidence: screen.score };
  }

  return { verdict: "clean", violationType: "none", confidence: 0.92 };
}

// ── Frame processing ──────────────────────────────────────────────────────────

async function processFrame(bitmap: ImageBitmap, snapshotId: string): Promise<void> {
  busy = true;
  const t0 = performance.now();

  try {
    if (!faceLandmarker) {
      throw new Error("FaceLandmarker not initialized");
    }

    const [faceResults, yoloDetections] = await Promise.all([
      Promise.resolve(faceLandmarker.detectForVideo(bitmap, performance.now())),
      runYolo(bitmap),
    ]);

    bitmap.close();

    const { verdict, violationType, confidence } = computeVerdict(faceResults, yoloDetections);
    const inferenceMs = Math.round(performance.now() - t0);

    const result: { type: "result" } & FrameResult = {
      type: "result",
      snapshotId,
      verdict,
      violationType,
      confidence,
      inferenceMs,
      modelVersion: currentModelVersion,
    };
    self.postMessage(result);
  } catch (err) {
    bitmap.close();
    self.postMessage({
      type: "error",
      snapshotId,
      message: err instanceof Error ? err.message : String(err),
    });
  } finally {
    busy = false;
    if (pendingFrame !== null) {
      const next = pendingFrame;
      pendingFrame = null;
      void processFrame(next.bitmap, next.snapshotId);
    }
  }
}

// ── Message handler ───────────────────────────────────────────────────────────

interface InitMessage {
  type: "init";
  mediapipeWasmUrl: string;
  taskModelUrl: string;
  onnxModelUrl: string;
  modelVersion: string;
}

interface InferMessage {
  type: "infer";
  frame: ImageBitmap;
  snapshotId: string;
}

type WorkerInMessage = InitMessage | InferMessage;

self.onmessage = async (event: MessageEvent<WorkerInMessage>) => {
  const msg = event.data;

  if (msg.type === "init") {
    const simdOk = await checkSimdSupport();
    if (!simdOk) {
      self.postMessage({ type: "unsupported", reason: "WASM SIMD not supported on this device" });
      return;
    }
    currentModelVersion = msg.modelVersion ?? "v0.0.0";
    try {
      await loadModels(msg.mediapipeWasmUrl, msg.taskModelUrl, msg.onnxModelUrl);
    } catch (err) {
      self.postMessage({
        type: "unsupported",
        reason: err instanceof Error ? err.message : String(err),
      });
    }
    return;
  }

  if (msg.type === "infer") {
    const { frame: bitmap, snapshotId } = msg;
    if (busy) {
      if (pendingFrame !== null) pendingFrame.bitmap.close();
      pendingFrame = { bitmap, snapshotId };
      return;
    }
    void processFrame(bitmap, snapshotId);
  }
};
