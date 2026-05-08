import { sessionOnlyStorage, storage } from "@/lib/storage";

export function clearAgentSnapshots() {
  if (typeof window === "undefined") return;

  storage.removeItem("forensic_initial_agents");
  storage.removeItem("forensic_deep_agents");

  Object.keys(window.localStorage).forEach((key) => {
    if (key.startsWith("forensic_initial_agents:") || key.startsWith("forensic_deep_agents:")) {
      window.localStorage.removeItem(key);
    }
  });
}

export function expireSessionCookie() {
  if (typeof document === "undefined") return;
  document.cookie = "forensic_session_id=; path=/; max-age=0; SameSite=Lax";
}

export function clearInvestigationPersistence() {
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
}
