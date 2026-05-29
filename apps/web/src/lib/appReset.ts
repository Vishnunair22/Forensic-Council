import type { QueryClient } from "@tanstack/react-query";
import { arbiterControl } from "@/lib/arbiterControl";
import { __pendingFileStore } from "@/lib/pendingFileStore";
import { clearPendingEvidenceFile } from "@/lib/pendingFilePersistence";
import { storage, sessionOnlyStorage } from "@/lib/storage";
import { readCookie, API_BASE } from "@/lib/api/utils";
import { STORAGE_KEYS } from "@/lib/storageKeys";

function expireCookie(name: string) {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=; path=/; max-age=0; SameSite=Lax`;
}

export function clearAuthCookies() {
  // access_token is httpOnly — JS cannot expire it directly.
  // The backend logout call in resetActiveInvestigation handles it via Set-Cookie.
  expireCookie("csrf_token");
  expireCookie("fc_session");
}

export function resetActiveInvestigation(queryClient?: QueryClient) {
  if (typeof window === "undefined") return;

  const csrfToken = readCookie("csrf_token");
  const mutationHeaders: Record<string, string> = {};
  if (csrfToken) {
    mutationHeaders["X-CSRF-Token"] = csrfToken;
  }

  // Terminate the backend pipeline for any running session before wiping local
  // state.  Fire-and-forget: local cleanup proceeds regardless of response.
  const runningSessionId = storage.getItem(STORAGE_KEYS.SESSION_ID);
  if (runningSessionId) {
    fetch(`${API_BASE}/api/v1/sessions/${encodeURIComponent(runningSessionId)}`, {
      method: "DELETE",
      credentials: "include",
      headers: mutationHeaders,
    }).catch(() => {});
  }

  // Expire the httpOnly access_token via backend Set-Cookie response.
  fetch(`${API_BASE}/api/v1/auth/logout`, {
    method: "POST",
    credentials: "include",
    headers: mutationHeaders,
  }).catch(() => {});

  arbiterControl.abort();
  queryClient?.clear();

  // Preserve history before wiping all forensic keys
  let savedHistory: unknown[] = [];
  try {
    const h = storage.getItem<unknown[]>(STORAGE_KEYS.HISTORY, true);
    if (Array.isArray(h)) savedHistory = h;
  } catch { /* ignore */ }

  storage.clearAllForensicKeys();
  sessionOnlyStorage.clearAllForensicKeys();

  if (savedHistory.length > 0) {
    storage.setItem(STORAGE_KEYS.HISTORY, savedHistory, true);
  }

  expireCookie(STORAGE_KEYS.SESSION_ID);
  clearAuthCookies();

  document.body.removeAttribute("data-fc-loading");
  document.body.style.overflow = "";

  __pendingFileStore.file = null;
  __pendingFileStore.authPromise = null;
  __pendingFileStore.authError = null;
  clearPendingEvidenceFile().catch(() => {});

  sessionOnlyStorage.setItem(STORAGE_KEYS.FC_NO_RECONNECT, "1");

  window.dispatchEvent(new Event("fc:reset-home"));
}
