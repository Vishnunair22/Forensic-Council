"use client";

const DB_NAME = "forensic-council-pending-upload";
const STORE_NAME = "pending";
const FILE_KEY = "evidence-file";

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("IndexedDB is unavailable"));
      return;
    }

    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME);
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Failed to open IndexedDB"));
  });
}

async function withStore<T>(
  mode: IDBTransactionMode,
  fn: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  const db = await openDb();
  try {
    return await new Promise<T>((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, mode);
      const request = fn(tx.objectStore(STORE_NAME));
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error ?? new Error("IndexedDB request failed"));
      tx.onerror = () => reject(tx.error ?? new Error("IndexedDB transaction failed"));
    });
  } finally {
    db.close();
  }
}

export async function savePendingEvidenceFile(file: File): Promise<void> {
  await withStore("readwrite", (store) => store.put(file, FILE_KEY));
}

export async function loadPendingEvidenceFile(): Promise<File | null> {
  const value = await withStore<File | undefined>("readonly", (store) => store.get(FILE_KEY));
  return value instanceof File ? value : null;
}

export async function clearPendingEvidenceFile(): Promise<void> {
  await withStore("readwrite", (store) => store.delete(FILE_KEY));
}
