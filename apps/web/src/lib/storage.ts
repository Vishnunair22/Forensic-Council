export const isBrowser = typeof window !== "undefined";
const isDev = process.env.NODE_ENV !== "production";

interface AppStorage {
  getItem(key: string, parseJson?: false, fallback?: string | null): string | null;
  getItem<T>(key: string, parseJson: true, fallback?: T | null): T | null;
  setItem(key: string, value: unknown, stringify?: boolean): void;
  removeItem(key: string): void;
}

function createStorage(store: Storage): AppStorage {
  return {
    getItem<T>(key: string, parseJson = false, fallback: T | string | null = null): any {
      if (!isBrowser) return fallback;
      try {
        const val = store.getItem(key);
        if (val === null) return fallback;
        if (parseJson) return JSON.parse(val);
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
