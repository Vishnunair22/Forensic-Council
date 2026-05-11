import type { QueryClient } from "@tanstack/react-query";
import { arbiterControl } from "@/lib/arbiterControl";
import { __pendingFileStore } from "@/lib/pendingFileStore";
import { storage, sessionOnlyStorage } from "@/lib/storage";

function expireCookie(name: string) {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=; path=/; max-age=0; SameSite=Lax`;
}

export function clearAuthCookies() {
  expireCookie("access_token");
  expireCookie("csrf_token");
  expireCookie("fc_session");
}

export function resetActiveInvestigation(queryClient?: QueryClient) {
  if (typeof window === "undefined") return;

  arbiterControl.abort();
  queryClient?.clear();

  storage.removeItem("forensic_session_id");
  storage.removeItem("forensic_investigation_ctx");
  storage.removeItem("forensic_thumbnail");
  storage.removeItem("forensic_mime_type");
  storage.removeItem("forensic_file_name");
  storage.removeItem("forensic_case_id");
  storage.removeItem("forensic_pipeline_start");
  storage.removeItem("forensic_hitl_checkpoint");
  storage.removeItem("forensic_auto_start");
  storage.removeItem("forensic_initial_agents");
  storage.removeItem("forensic_deep_agents");

  Object.keys(localStorage).forEach((key) => {
    if (
      key.startsWith("forensic_initial_agents:") ||
      key.startsWith("forensic_deep_agents:")
    ) {
      localStorage.removeItem(key);
    }
  });

  expireCookie("forensic_session_id");
  clearAuthCookies();

  document.body.removeAttribute("data-fc-loading");
  document.body.style.overflow = "";

  __pendingFileStore.file = null;
  __pendingFileStore.authPromise = null;

  sessionOnlyStorage.removeItem("fc_show_loading");
  sessionOnlyStorage.removeItem("fc_no_reconnect");
  sessionOnlyStorage.setItem("fc_no_reconnect", "1");

  window.dispatchEvent(new Event("fc:reset-home"));
}