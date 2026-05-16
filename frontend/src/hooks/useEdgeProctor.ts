"use client";

import { useCallback, useEffect, useRef } from "react";

export type EdgeViolationType =
  | "none"
  | "no_face"
  | "multiple_people"
  | "looking_away"
  | "phone_detected"
  | "another_screen";

export interface EdgeResult {
  snapshotId: string;
  verdict: "clean" | "flagged" | "uncertain" | "error";
  violationType: EdgeViolationType;
  confidence: number;
  inferenceMs: number;
  modelVersion: string;
}

interface UseEdgeProctorOptions {
  enabled: boolean;
  mediapipeWasmUrl: string;
  taskModelUrl: string;
  onnxModelUrl: string;
  modelVersion: string;
  onReady?: () => void;
  onUnsupported?: (reason: string) => void;
  onResult?: (result: EdgeResult) => void;
}

export function useEdgeProctor(opts: UseEdgeProctorOptions): {
  sendFrame: (video: HTMLVideoElement, snapshotId: string) => void;
} {
  const workerRef = useRef<Worker | null>(null);

  const sendFrame = useCallback((video: HTMLVideoElement, snapshotId: string) => {
    if (!workerRef.current || !video.videoWidth) return;
    createImageBitmap(video)
      .then((bitmap) => {
        workerRef.current?.postMessage({ type: "infer", frame: bitmap, snapshotId }, [bitmap]);
      })
      .catch(console.error);
  }, []);

  useEffect(() => {
    if (!opts.enabled || typeof Worker === "undefined") return;

    const worker = new Worker(
      new URL("../workers/EdgeProctorWorker.ts", import.meta.url),
    );
    workerRef.current = worker;

    worker.onmessage = (e: MessageEvent) => {
      const msg = e.data as { type: string } & EdgeResult & { reason?: string };
      if (msg.type === "ready") opts.onReady?.();
      if (msg.type === "unsupported") opts.onUnsupported?.(msg.reason ?? "unknown");
      if (msg.type === "result") opts.onResult?.(msg as EdgeResult);
    };

    worker.onerror = (err) => opts.onUnsupported?.(err.message ?? "worker error");

    worker.postMessage({
      type: "init",
      mediapipeWasmUrl: opts.mediapipeWasmUrl,
      taskModelUrl: opts.taskModelUrl,
      onnxModelUrl: opts.onnxModelUrl,
      modelVersion: opts.modelVersion,
    });

    return () => {
      worker.terminate();
      workerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opts.enabled]);

  return { sendFrame };
}
