"use client";

import { useEffect, useRef } from "react";
import { getSnapshotUploadUrl, recordSnapshot } from "@/lib/api";

export function useWebcamProctor(
  sessionId: string | null,
  sessionToken: string | null,
  enabled: boolean,
  intervalMs: number = 10_000,
) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  // Start/stop webcam stream
  useEffect(() => {
    if (!enabled || !sessionId || !sessionToken) return;

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

      canvas.toBlob(
        async (blob) => {
          if (!blob) return;
          const snapshotId = crypto.randomUUID();
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
            await recordSnapshot(sessionId, snapshotId, storage_key);
          } catch (e) {
            console.error("Snapshot upload failed:", e);
          }
        },
        "image/jpeg",
        0.8,
      );
    };

    const snapshotInterval = setInterval(captureSnapshot, intervalMs);
    return () => clearInterval(snapshotInterval);
  }, [enabled, sessionId, sessionToken, intervalMs]);

  // Heartbeat loop (every 30s via sendBeacon)
  useEffect(() => {
    if (!enabled || !sessionId || !sessionToken) return;

    const sendHeartbeatBeacon = () => {
      const url = `${process.env.NEXT_PUBLIC_EXAM_API_URL}/proctor/sessions/${sessionId}/heartbeat`;
      const blob = new Blob([JSON.stringify({})], { type: "application/json" });
      navigator.sendBeacon(url, blob);
    };

    const heartbeatInterval = setInterval(sendHeartbeatBeacon, 30_000);
    return () => clearInterval(heartbeatInterval);
  }, [enabled, sessionId, sessionToken]);

  return { videoRef };
}
