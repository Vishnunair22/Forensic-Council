import { sessionOnlyStorage, storage } from "@/lib/storage";
import { STORAGE_KEYS } from "@/lib/storageKeys";
import type { HistoryItem } from "@/lib/types";

function _saveHistory(): HistoryItem[] {
  try {
    return storage.getItem<HistoryItem[]>(STORAGE_KEYS.HISTORY, true, []) ?? [];
  } catch {
    return [];
  }
}

function _restoreHistory(history: HistoryItem[]) {
  if (history.length > 0) {
    storage.setItem(STORAGE_KEYS.HISTORY, history, true);
  }
}

export function clearAgentSnapshots() {
  if (typeof window === "undefined") return;

  storage.removeItem(STORAGE_KEYS.INITIAL_AGENTS);
  storage.removeItem(STORAGE_KEYS.DEEP_AGENTS);

  const keysToRemove: string[] = [];
  for (let i = 0; i < window.localStorage.length; i++) {
    const key = window.localStorage.key(i);
    if (
      key &&
      (key.startsWith(`${STORAGE_KEYS.INITIAL_AGENTS}:`) ||
        key.startsWith(`${STORAGE_KEYS.DEEP_AGENTS}:`) ||
        key.startsWith(`${STORAGE_KEYS.INVESTIGATION_CTX}:`))
    ) {
      keysToRemove.push(key);
    }
  }
  keysToRemove.forEach((key) => window.localStorage.removeItem(key));
}

export function expireSessionCookie() {
  if (typeof document === "undefined") return;
  document.cookie = `${STORAGE_KEYS.SESSION_ID}=; path=/; max-age=0; SameSite=Lax`;
}

export function clearInvestigationPersistence() {
  const savedHistory = _saveHistory();

  [
    STORAGE_KEYS.SESSION_ID,
    STORAGE_KEYS.INVESTIGATION_CTX,
    STORAGE_KEYS.THUMBNAIL,
    STORAGE_KEYS.MIME_TYPE,
    STORAGE_KEYS.FILE_NAME,
    STORAGE_KEYS.CASE_ID,
    STORAGE_KEYS.PIPELINE_START,
    STORAGE_KEYS.HITL_CHECKPOINT,
    STORAGE_KEYS.IS_DEEP,
  ].forEach((key) => {
    storage.removeItem(key);
    sessionOnlyStorage.removeItem(key);
  });

  clearAgentSnapshots();
  expireSessionCookie();
  _restoreHistory(savedHistory);
}
