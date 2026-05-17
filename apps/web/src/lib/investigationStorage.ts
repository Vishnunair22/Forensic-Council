import { sessionOnlyStorage, storage } from "@/lib/storage";
import type { HistoryItem } from "@/lib/types";

function _saveHistory(): HistoryItem[] {
  try {
    return storage.getItem<HistoryItem[]>("forensic_history", true, []) ?? [];
  } catch {
    return [];
  }
}

function _restoreHistory(history: HistoryItem[]) {
  if (history.length > 0) {
    storage.setItem("forensic_history", history, true);
  }
}

export function clearAgentSnapshots() {
  if (typeof window === "undefined") return;

  storage.removeItem("forensic_initial_agents");
  storage.removeItem("forensic_deep_agents");

  const keysToRemove: string[] = [];
  for (let i = 0; i < window.localStorage.length; i++) {
    const key = window.localStorage.key(i);
    if (key && (key.startsWith("forensic_initial_agents:") || key.startsWith("forensic_deep_agents:") || key.startsWith("forensic_investigation_ctx:"))) {
      keysToRemove.push(key);
    }
  }
  keysToRemove.forEach((key) => window.localStorage.removeItem(key));
}

export function expireSessionCookie() {
  if (typeof document === "undefined") return;
  document.cookie = "forensic_session_id=; path=/; max-age=0; SameSite=Lax";
}

export function clearInvestigationPersistence() {
  const savedHistory = _saveHistory();

  [
    "forensic_session_id",
    "forensic_investigation_ctx",
    "forensic_thumbnail",
    "forensic_mime_type",
    "forensic_file_name",
    "forensic_case_id",
    "forensic_pipeline_start",
    "forensic_hitl_checkpoint",
    "forensic_is_deep",
  ].forEach((key) => {
    storage.removeItem(key);
    sessionOnlyStorage.removeItem(key);
  });

  clearAgentSnapshots();
  expireSessionCookie();
  _restoreHistory(savedHistory);
}
