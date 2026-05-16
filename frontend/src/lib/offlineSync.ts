"use client";

import {
  getOfflineFramesByPriority,
  markFrameUploaded,
  type OfflineFrame,
} from "@/lib/offlineDb";
import { apiFetch } from "@/lib/api";

const BATCH_SIZE = 50;

interface BatchUrlItem {
  snapshot_id: string;
  upload_url: string;
  storage_key: string;
}

async function getBatchUploadUrls(
  sessionId: string,
  sessionToken: string,
  frames: OfflineFrame[],
): Promise<BatchUrlItem[]> {
  const result = await apiFetch<{ urls: BatchUrlItem[] }>(
    `/proctor/sessions/${sessionId}/offline-frames/batch-upload-urls`,
    {
      method: "POST",
      headers: { "X-Session-Token": sessionToken },
      body: JSON.stringify({
        frames: frames.map((f) => ({
          snapshot_id: f.snapshot_id,
          taken_at: new Date(f.captured_at).toISOString(),
        })),
      }),
    },
  );
  return result.urls;
}

async function confirmBatchRecorded(
  sessionId: string,
  sessionToken: string,
  frames: OfflineFrame[],
): Promise<void> {
  await apiFetch(`/proctor/sessions/${sessionId}/offline-frames/batch-recorded`, {
    method: "POST",
    headers: { "X-Session-Token": sessionToken },
    body: JSON.stringify({
      frames: frames.map((f, idx) => ({
        snapshot_id: f.snapshot_id,
        frame_seq: idx,
        edge_classification: f.edge_classification,
        taken_at: new Date(f.captured_at).toISOString(),
      })),
    }),
  });
}

export async function drain(
  sessionId: string,
  sessionToken: string,
  db: IDBDatabase,
  onProgress?: (uploaded: number, total: number) => void,
): Promise<void> {
  const frames = await getOfflineFramesByPriority(db, sessionId);
  if (frames.length === 0) return;

  const total = frames.length;
  let uploaded = 0;

  for (let i = 0; i < frames.length; i += BATCH_SIZE) {
    const batch = frames.slice(i, i + BATCH_SIZE);

    // Get presigned URLs
    const urls = await getBatchUploadUrls(sessionId, sessionToken, batch);

    // Upload each frame to MinIO in parallel
    await Promise.all(
      urls.map(async (item) => {
        const frame = batch.find((f) => f.snapshot_id === item.snapshot_id);
        if (!frame) return;
        await fetch(item.upload_url, {
          method: "PUT",
          body: frame.blob,
          headers: { "Content-Type": "image/jpeg" },
        });
      }),
    );

    // Confirm batch uploaded
    await confirmBatchRecorded(sessionId, sessionToken, batch);

    // Mark each frame as uploaded in IndexedDB
    await Promise.all(batch.map((f) => markFrameUploaded(db, f.snapshot_id)));

    uploaded += batch.length;
    onProgress?.(uploaded, total);
  }
}
