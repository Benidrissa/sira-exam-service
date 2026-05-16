"use client";

const DB_NAME = "sira-offline-proctor";
const DB_VERSION = 1;

// ── Types ────────────────────────────────────────────────────────────────────

export interface OfflineFrame {
  snapshot_id: string;
  session_id: string;
  captured_at: number; // Unix ms
  blob: Blob;
  edge_classification: "clean" | "flagged" | "unknown";
  edge_confidence: number;
  upload_attempts: number;
  uploaded: boolean;
}

export interface OfflineHeartbeat {
  sequence_number?: number; // auto-increment
  session_id: string;
  scheduled_at: number; // Unix ms
  reported: boolean;
}

export interface OfflineMetadata {
  session_id: string;
  network_dropped_at: number | null;
  network_resumed_at: number | null;
  total_offline_ms: number;
  drain_in_progress: boolean;
  last_successful_heartbeat_at: number;
}

// ── Open DB ───────────────────────────────────────────────────────────────────

export async function openOfflineDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("IndexedDB not available"));
      return;
    }
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;

      // offline_frames store
      if (!db.objectStoreNames.contains("offline_frames")) {
        const framesStore = db.createObjectStore("offline_frames", {
          keyPath: "snapshot_id",
        });
        framesStore.createIndex("by_session_id", "session_id");
        framesStore.createIndex("by_captured_at", "captured_at");
        framesStore.createIndex("by_uploaded", ["session_id", "uploaded"]);
      }

      // offline_heartbeats store
      if (!db.objectStoreNames.contains("offline_heartbeats")) {
        const hbStore = db.createObjectStore("offline_heartbeats", {
          keyPath: "sequence_number",
          autoIncrement: true,
        });
        hbStore.createIndex("by_session_id", "session_id");
      }

      // offline_metadata store
      if (!db.objectStoreNames.contains("offline_metadata")) {
        db.createObjectStore("offline_metadata", { keyPath: "session_id" });
      }
    };

    request.onsuccess = () => {
      const db = request.result;
      // Request persistent storage to prevent eviction
      if (navigator.storage?.persist) {
        void navigator.storage.persist();
      }
      resolve(db);
    };
    request.onerror = () => reject(request.error);
  });
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function txStore(db: IDBDatabase, storeName: string, mode: IDBTransactionMode): IDBObjectStore {
  return db.transaction(storeName, mode).objectStore(storeName);
}

function promisify<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

// ── Frames ────────────────────────────────────────────────────────────────────

export async function putOfflineFrame(db: IDBDatabase, frame: OfflineFrame): Promise<void> {
  await promisify(txStore(db, "offline_frames", "readwrite").put(frame));
}

export async function getOfflineFramesByPriority(
  db: IDBDatabase,
  sessionId: string,
): Promise<OfflineFrame[]> {
  const store = txStore(db, "offline_frames", "readonly");
  const index = store.index("by_session_id");
  const all = await promisify(index.getAll(sessionId) as IDBRequest<OfflineFrame[]>);
  const pending = all.filter((f) => !f.uploaded);
  // Flagged frames first, then FIFO by captured_at
  return pending.sort((a, b) => {
    if (a.edge_classification === "flagged" && b.edge_classification !== "flagged") return -1;
    if (a.edge_classification !== "flagged" && b.edge_classification === "flagged") return 1;
    return a.captured_at - b.captured_at;
  });
}

export async function markFrameUploaded(db: IDBDatabase, snapshotId: string): Promise<void> {
  const store = db.transaction("offline_frames", "readwrite").objectStore("offline_frames");
  const frame = await promisify(store.get(snapshotId) as IDBRequest<OfflineFrame | undefined>);
  if (frame) {
    frame.uploaded = true;
    await promisify(store.put(frame));
  }
}

export async function clearUploadedFrames(db: IDBDatabase, sessionId: string): Promise<void> {
  const store = db.transaction("offline_frames", "readwrite").objectStore("offline_frames");
  const index = store.index("by_session_id");
  const all = await promisify(index.getAll(sessionId) as IDBRequest<OfflineFrame[]>);
  await Promise.all(
    all.filter((f) => f.uploaded).map((f) => promisify(store.delete(f.snapshot_id))),
  );
}

// ── Heartbeats ────────────────────────────────────────────────────────────────

export async function putHeartbeat(
  db: IDBDatabase,
  hb: Omit<OfflineHeartbeat, "sequence_number">,
): Promise<void> {
  await promisify(txStore(db, "offline_heartbeats", "readwrite").put(hb));
}

// ── Metadata ──────────────────────────────────────────────────────────────────

export async function getOfflineMetadata(
  db: IDBDatabase,
  sessionId: string,
): Promise<OfflineMetadata | null> {
  const result = await promisify(
    txStore(db, "offline_metadata", "readonly").get(sessionId) as IDBRequest<
      OfflineMetadata | undefined
    >,
  );
  return result ?? null;
}

export async function updateOfflineMetadata(
  db: IDBDatabase,
  sessionId: string,
  patch: Partial<OfflineMetadata>,
): Promise<void> {
  const store = db.transaction("offline_metadata", "readwrite").objectStore("offline_metadata");
  const existing = await promisify(
    store.get(sessionId) as IDBRequest<OfflineMetadata | undefined>,
  );
  const updated: OfflineMetadata = {
    session_id: sessionId,
    network_dropped_at: null,
    network_resumed_at: null,
    total_offline_ms: 0,
    drain_in_progress: false,
    last_successful_heartbeat_at: Date.now(),
    ...existing,
    ...patch,
  };
  await promisify(store.put(updated));
}
