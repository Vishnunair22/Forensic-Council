import type { QueryClient } from "@tanstack/react-query";
import { arbiterControl } from "@/lib/arbiterControl";
import { __pendingFileStore } from "@/lib/pendingFileStore";
import { clearPendingEvidenceFile } from "@/lib/pendingFilePersistence";
import { storage, sessionOnlyStorage } from "@/lib/storage";
import { readCookie, API_BASE, getMutationHeaders } from "@/lib/api/utils";
import { STORAGE_KEYS } from "@/lib/storageKeys";

function expireCookie(name: string) {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=; path=/; max-age=0; SameSite=Lax`;
}

export function clearAuthCookies() {
  expireCookie("csrf_token");
  expireCookie("fc_session");
}

function getCurrentSessionIdFromUrl(): string | null {
  if (typeof window === "undefined") return null;
  const match = window.location.pathname.match(/^\/result\/([^/?#]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

export function resolveActiveSessionId(): string | null {
  if (typeof window === "undefined") return null;
  return (
    storage.getItem(STORAGE_KEYS.SESSION_ID) ??
    getCurrentSessionIdFromUrl() ??
    readCookie(STORAGE_KEYS.SESSION_ID)
  );
}

export function hasResettableInvestigationState(): boolean {
  if (typeof window === "undefined") return false;
  return Boolean(
    storage.getItem(STORAGE_KEYS.SESSION_ID) ||
    readCookie(STORAGE_KEYS.SESSION_ID) ||
    window.location.pathname.match(/^\/result\/[^/?#]+/) ||
    sessionOnlyStorage.getItem(STORAGE_KEYS.AUTO_START) === "true" ||
    sessionOnlyStorage.getItem(STORAGE_KEYS.FC_SHOW_LOADING) === "true" ||
    sessionOnlyStorage.getItem(STORAGE_KEYS.FC_PENDING_FILE_META)
  );
}

export function cleanupLocalInvestigationState(queryClient?: QueryClient) {
  arbiterControl.abort();
  queryClient?.clear();

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

export async function resetActiveInvestigation(queryClient?: QueryClient) {
  if (typeof window === "undefined") return;

  const runningSessionId = resolveActiveSessionId();

  let mutationHeaders: Headers | undefined;
  try {
    mutationHeaders = await getMutationHeaders();
  } catch {
    mutationHeaders = undefined;
  }

  const terminatePromise = runningSessionId
    ? fetch(`${API_BASE}/api/v1/sessions/${encodeURIComponent(runningSessionId)}`, {
        method: "DELETE",
        credentials: "include",
        headers: mutationHeaders,
        keepalive: true,
      }).catch(() => null)
    : Promise.resolve(null);

  const logoutPromise = fetch(`${API_BASE}/api/v1/auth/logout`, {
    method: "POST",
    credentials: "include",
    headers: mutationHeaders,
    keepalive: true,
  }).catch(() => null);

  cleanupLocalInvestigationState(queryClient);

  await Promise.race([
    Promise.allSettled([terminatePromise, logoutPromise]),
    new Promise((resolve) => setTimeout(resolve, 800)),
  ]);
}
