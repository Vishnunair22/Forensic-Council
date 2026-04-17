export const isBrowser = typeof window !== "undefined";

function createStorage(store: Storage) {
  return {
    getItem<T>(key: string, parseJson = false, fallback: T | null = null): T | null {
      if (!isBrowser) return fallback;
      try {
        const val = store.getItem(key);
        if (val === null) return fallback;
        if (parseJson) return JSON.parse(val) as T;
        return val as unknown as T;
      } catch (e: unknown) {
        console.warn(`[storage] Error reading key "${key}":`, e);
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
        console.warn(`[storage] Error writing key "${key}":`, e);
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
        console.warn(`[storage] Error removing key "${key}":`, e);
      }
    },
  };
}

export const persistentStorage = isBrowser ? createStorage(window.localStorage) : createStorage({} as Storage);
export const sessionOnlyStorage = isBrowser ? createStorage(window.sessionStorage) : createStorage({} as Storage);
export const storage = persistentStorage;
