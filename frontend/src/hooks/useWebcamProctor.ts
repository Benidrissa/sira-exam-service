"use client";

import { useEffect, useRef } from "react";
import { getSnapshotUploadUrl, recordSnapshot } from "@/lib/api";
import type { EdgeResult } from "@/hooks/useEdgeProctor";

export function useWebcamProctor(
  sessionId: string | null,
  sessionToken: string | null,
  enabled: boolean,
  intervalMs: number = 10_000,
  connectivityState?: import("@/hooks/useConnectivityProbe").ConnectivityState,
  offlineDb?: IDBDatabase | null,
  aiTier?: 0 | 1 | 2,
  vlmConfig?: import("@/types/exam").VLMConfigResponse | null,
  onEdgeResult?: (result: EdgeResult) => void,
) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  // Edge AI result store: snapshotId → EdgeResult (populated by registerEdgeResult)
  const edgeResultsRef = useRef<Map<string, EdgeResult>>(new Map());
  const frameSeqRef = useRef(0);
  const prevSnapshotIdRef = useRef<string | null>(null);

  // Start/stop webcam stream
  useEffect(() => {
    if (!enabled || !sessionId || !sessionToken) return;

    if (sessionToken) {
      sessionStorage.setItem("proctor_session_token", sessionToken);
    }
    if (sessionId) {
      sessionStorage.setItem("proctor_session_id", sessionId);
    }

    navigator.mediaDevices
      .getUserMedia({ video: true, audio: false })
      .then((stream) => {
        streamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;
      })
      .catch((err) => console.error("Webcam access denied:", err));

    return () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
  }, [enabled, sessionId, sessionToken]);

  // Snapshot capture loop
  useEffect(() => {
    if (!enabled || !sessionId || !sessionToken) return;

    const captureSnapshot = async () => {
      const video = videoRef.current;
      if (!video || !video.videoWidth) return;

      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      canvas.getContext("2d")?.drawImage(video, 0, 0);

      // If offline, write to IndexedDB instead of uploading
      if (connectivityState && connectivityState !== "ONLINE" && offlineDb) {
        const { putOfflineFrame } = await import("@/lib/offlineDb");
        canvas.toBlob(async (blob) => {
          if (!blob) return;
          await putOfflineFrame(offlineDb, {
            snapshot_id: crypto.randomUUID(),
            session_id: sessionId!,
            captured_at: Date.now(),
            blob,
            edge_classification: "unknown",
            edge_confidence: 0,
            upload_attempts: 0,
            uploaded: false,
          });
        }, "image/jpeg", 0.8);
        return; // skip normal upload
      }

      canvas.toBlob(
        async (blob) => {
          if (!blob) return;

          // Increment frame sequence for this capture
          frameSeqRef.current += 1;
          const currentSeq = frameSeqRef.current;
          const snapshotId = crypto.randomUUID();

          // SHA-256 of the blob bytes (before upload)
          let frameSha256: string | undefined;
          try {
            const arrayBuffer = await blob.arrayBuffer();
            const hashBuffer = await crypto.subtle.digest("SHA-256", arrayBuffer);
            frameSha256 = Array.from(new Uint8Array(hashBuffer))
              .map((b) => b.toString(16).padStart(2, "0"))
              .join("");
          } catch {
            frameSha256 = undefined;
          }

          // One-frame lag: use the edge result from the PREVIOUS snapshot
          // (allows the worker inference to complete before we attach the verdict)
          const prevEdgeResult = prevSnapshotIdRef.current
            ? edgeResultsRef.current.get(prevSnapshotIdRef.current)
            : undefined;

          try {
            const { upload_url, storage_key } = await getSnapshotUploadUrl(
              sessionId,
              snapshotId,
            );
            await fetch(upload_url, {
              method: "PUT",
              body: blob,
              headers: { "Content-Type": "image/jpeg" },
            });
            await recordSnapshot(sessionId, snapshotId, storage_key, {
              frame_sha256: frameSha256,
              frame_sequence_number: currentSeq,
              edge_verdict: prevEdgeResult?.verdict ?? undefined,
              edge_confidence: prevEdgeResult?.confidence ?? undefined,
              edge_violation_type: prevEdgeResult?.violationType ?? undefined,
              edge_model_version: prevEdgeResult?.modelVersion ?? undefined,
              is_offline_frame: false,
              edge_processed: !!prevEdgeResult,
            });
          } catch (e) {
            console.error("Snapshot upload failed:", e);
          }

          // Track this snapshot as "previous" for the next capture cycle
          prevSnapshotIdRef.current = snapshotId;

          // Notify caller to dispatch frame to edge worker (play/page.tsx wires this)
          if (onEdgeResult && aiTier && aiTier > 0 && video.videoWidth) {
            // Caller receives a stub so it can correlate the snapshotId
            // Actual inference result will come back via registerEdgeResult()
            onEdgeResult({
              snapshotId,
              verdict: "uncertain",
              violationType: "none",
              confidence: 0,
              inferenceMs: 0,
              modelVersion: vlmConfig?.model_version ?? "",
            });
          }
        },
        "image/jpeg",
        0.8,
      );
    };

    const snapshotInterval = setInterval(captureSnapshot, intervalMs);
    return () => clearInterval(snapshotInterval);
  }, [enabled, sessionId, sessionToken, intervalMs, connectivityState, offlineDb, aiTier, vlmConfig, onEdgeResult]);

  // Heartbeat loop (every 30s — keepalive fetch so headers can be set; sendBeacon cannot)
  useEffect(() => {
    if (!enabled || !sessionId || !sessionToken) return;

    const sendHeartbeat = () => {
      const match =
        typeof document !== "undefined"
          ? document.cookie.match(/(?:^|; )access_token=([^;]*)/)
          : null;
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        "X-Session-Token": sessionToken,
      };
      if (match) {
        headers["Authorization"] = `Bearer ${decodeURIComponent(match[1])}`;
      }

      fetch(
        `${process.env.NEXT_PUBLIC_EXAM_API_URL}/proctor/sessions/${sessionId}/heartbeat`,
        {
          method: "POST",
          keepalive: true,
          headers,
          body: JSON.stringify({}),
          credentials: "include",
        },
      ).catch((e) => console.error("Heartbeat failed:", e));
    };

    const heartbeatInterval = setInterval(sendHeartbeat, 30_000);
    return () => clearInterval(heartbeatInterval);
  }, [enabled, sessionId, sessionToken]);

  /**
   * Called by play/page.tsx after receiving an EdgeResult from useEdgeProctor.
   * Stores the result so the NEXT snapshot capture can attach it to its POST body.
   */
  const registerEdgeResult = (snapshotId: string, result: EdgeResult) => {
    edgeResultsRef.current.set(snapshotId, result);
  };

  return { videoRef, registerEdgeResult };
}
