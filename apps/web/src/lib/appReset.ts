import type { QueryClient } from "@tanstack/react-query";
import { arbiterControl } from "@/lib/arbiterControl";
import { __pendingFileStore } from "@/lib/pendingFileStore";
import { clearPendingEvidenceFile } from "@/lib/pendingFilePersistence";
import { storage, sessionOnlyStorage } from "@/lib/storage";
import { readCookie } from "@/lib/api/utils";
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

  // Expire the httpOnly access_token via backend Set-Cookie response (fire-and-forget).
  // Must run before clearAuthCookies() wipes csrf_token.
  const csrfToken = readCookie("csrf_token");
  fetch("/api/v1/auth/logout", {
    method: "POST",
    credentials: "include",
    headers: csrfToken ? { "X-CSRF-Token": csrfToken } : {},
  }).catch(() => {});

  arbiterControl.abort();
  queryClient?.clear();

  // Preserve history before wiping all forensic keys
  let savedHistory: unknown[] = [];
  try {
    const h = storage.getItem<unknown[]>("forensic_history", true);
    if (Array.isArray(h)) savedHistory = h;
  } catch { /* ignore */ }

  storage.clearAllForensicKeys();
  sessionOnlyStorage.clearAllForensicKeys();

  if (savedHistory.length > 0) {
    storage.setItem("forensic_history", savedHistory, true);
  }

  expireCookie("forensic_session_id");
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
