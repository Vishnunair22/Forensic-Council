export const isBrowser = typeof window !== "undefined";
const isDev = process.env.NODE_ENV !== "production";

interface AppStorage {
  getItem(key: string, parseJson?: false, fallback?: string | null): string | null;
  getItem<T>(key: string, parseJson: true, fallback?: T | null): T | null;
  setItem(key: string, value: unknown, stringify?: boolean): void;
  removeItem(key: string): void;
  clearAllForensicKeys(keepHistory?: boolean): void;
}

function _pruneOldForensicKeys(store: Storage): number {
  const forensicPrefixes = ["forensic_", "fc_"];
  const preserveKeys = new Set([
    "forensic_investigator_id",
    "forensic_history",
    "forensic_session_id",
  ]);
  const keysToRemove: { key: string; age: number }[] = [];
  for (let i = 0; i < store.length; i++) {
    const key = store.key(i);
    if (!key || !forensicPrefixes.some((p) => key.startsWith(p))) continue;
    if (preserveKeys.has(key)) continue;
    try {
      const raw = store.getItem(key);
      const parsed = raw ? JSON.parse(raw) : null;
      const ts = parsed?.updatedAt ?? parsed?.timestamp ?? 0;
      keysToRemove.push({ key, age: ts ? Date.now() - ts : Infinity });
    } catch {
      keysToRemove.push({ key, age: Infinity });
    }
  }
  keysToRemove.sort((a, b) => b.age - a.age);
  let pruned = 0;
  for (const { key } of keysToRemove.slice(0, Math.max(20, Math.floor(keysToRemove.length / 2)))) {
    try {
      store.removeItem(key);
      pruned++;
    } catch {
      /* single key removal failure is non-fatal */
    }
  }
  return pruned;
}

function createStorage(store: Storage): AppStorage {
  return {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    getItem<T>(key: string, parseJson = false, fallback: T | string | null = null): any {
      if (!isBrowser) return fallback;
      try {
        const val = store.getItem(key);
        if (val === null) return fallback;
        if (parseJson) {
          const trimmed = val.trim();
          if (!trimmed) return fallback;
          return JSON.parse(trimmed);
        }
        return val;
      } catch (e: unknown) {
        if (isDev) console.warn(`[storage] Error reading key "${key}":`, e);
        return fallback;
      }
    },

    setItem(key: string, value: unknown, stringify = false): void {
      if (!isBrowser) return;
      try {
        const val = stringify ? JSON.stringify(value) : String(value);
        store.setItem(key, val);
        window.dispatchEvent(
          new CustomEvent("fc_storage_update", { detail: { key, value: val } })
        );
      } catch (e: unknown) {
        if (isDev) console.warn(`[storage] Error writing key "${key}":`, e);
        const isQuota =
          e instanceof DOMException &&
          (e.name === "QuotaExceededError" || e.name === "NS_ERROR_DOM_QUOTA_REACHED");
        if (isQuota) {
          // F-11: try to reclaim space by pruning old forensic keys, then retry once.
          try {
            const pruned = _pruneOldForensicKeys(store);
            if (pruned > 0) {
              const val = stringify ? JSON.stringify(value) : String(value);
              store.setItem(key, val);
              window.dispatchEvent(
                new CustomEvent("fc_storage_update", { detail: { key, value: val } })
              );
              return;
            }
          } catch {
            // retry failed — fall through to quota-exceeded notification
          }
          window.dispatchEvent(new CustomEvent("fc_storage_quota_exceeded", { detail: { key } }));
        }
      }
    },

    removeItem(key: string): void {
      if (!isBrowser) return;
      try {
        store.removeItem(key);
        window.dispatchEvent(
          new CustomEvent("fc_storage_update", { detail: { key, value: null } })
        );
      } catch (e: unknown) {
        if (isDev) console.warn(`[storage] Error removing key "${key}":`, e);
      }
    },

    clearAllForensicKeys(keepHistory = false): void {
      if (!isBrowser) return;
      try {
        const keysToRemove: string[] = [];
        for (let i = 0; i < store.length; i++) {
          const key = store.key(i);
          if ((key?.startsWith("forensic_") || key?.startsWith("fc_")) && key !== "forensic_investigator_id") {
            if (keepHistory && key === "forensic_history") continue;
            keysToRemove.push(key);
          }
        }
        keysToRemove.forEach(k => {
          store.removeItem(k);
          window.dispatchEvent(
            new CustomEvent("fc_storage_update", { detail: { key: k, value: null } })
          );
        });
      } catch (e: unknown) {
        if (isDev) console.warn("[storage] Error clearing forensic keys:", e);
      }
    },
  };
}

const noopStorage: Storage = {
  length: 0,
  clear: () => {},
  getItem: () => null,
  key: () => null,
  removeItem: () => {},
  setItem: () => {},
};

export const persistentStorage = createStorage(isBrowser ? window.localStorage : noopStorage);
export const sessionOnlyStorage = createStorage(isBrowser ? window.sessionStorage : noopStorage);
export const storage = persistentStorage;
