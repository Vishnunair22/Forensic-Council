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

// Per-session key prefixes that hold display CONTEXT (not findings). These are
// preserved for sessions still in History so a revisit renders correct file
// metadata, and pruned only when the session leaves History.
const SESSION_SCOPED_CONTEXT_PREFIXES = [
  STORAGE_KEYS.INVESTIGATION_CTX,
  STORAGE_KEYS.THUMBNAIL,
  STORAGE_KEYS.MIME_TYPE,
  STORAGE_KEYS.FILE_NAME,
  STORAGE_KEYS.PIPELINE_START,
  STORAGE_KEYS.RESULT_PHASE,
  STORAGE_KEYS.EVIDENCE_SHA256,
] as const;

// Session-only (sessionStorage) per-session flags.
const SESSION_SCOPED_TRANSIENT_PREFIXES = [
  STORAGE_KEYS.FC_REPORT_READY,
  STORAGE_KEYS.FC_ARBITER_TRANSITIONING,
  STORAGE_KEYS.FC_RESUME_REQUESTED,
] as const;

// Per-session key prefixes that hold streamed agent FINDINGS. These are stale-
// prone and must never leak into a later investigation, so they are swept for
// ALL sessions. Revisits rebuild the timeline from the authoritative report.
const SESSION_SCOPED_FINDING_PREFIXES = [
  STORAGE_KEYS.INITIAL_AGENTS,
  STORAGE_KEYS.DEEP_AGENTS,
] as const;

function _historySessionIds(): Set<string> {
  try {
    const hist = storage.getItem<HistoryItem[]>(STORAGE_KEYS.HISTORY, true, []) ?? [];
    return new Set(hist.map((h) => h.sessionId).filter(Boolean));
  } catch {
    return new Set();
  }
}

// Sweep all "<prefix>:<sid>" keys across the given stores. When keepSids is
// provided, keys whose sid is in the set are preserved. Keys are collected
// before removal so live index shifting during iteration cannot skip entries.
function _sweepScopedKeys(
  prefixes: readonly string[],
  stores: Storage[],
  keepSids?: Set<string>,
) {
  for (const store of stores) {
    const toRemove: string[] = [];
    for (let i = 0; i < store.length; i++) {
      const key = store.key(i);
      if (!key) continue;
      for (const prefix of prefixes) {
        if (key.startsWith(`${prefix}:`)) {
          if (!keepSids || !keepSids.has(key.slice(prefix.length + 1))) {
            toRemove.push(key);
          }
          break;
        }
      }
    }
    toRemove.forEach((key) => {
      try {
        store.removeItem(key);
      } catch {
        /* single key removal failure is non-fatal */
      }
    });
  }
}

export function clearAgentSnapshots() {
  if (typeof window === "undefined") return;

  storage.removeItem(STORAGE_KEYS.INITIAL_AGENTS);
  storage.removeItem(STORAGE_KEYS.DEEP_AGENTS);

  // Sweep streamed agent findings for EVERY session — these are the stale-prone
  // payload. Context keys are intentionally left to pruneOrphanScopedKeys so a
  // History revisit still renders the correct file metadata.
  _sweepScopedKeys(SESSION_SCOPED_FINDING_PREFIXES, [window.localStorage]);
}

// Bound unbounded accumulation: drop every session-scoped key whose session is
// no longer reachable (not in History and not the active session). This removes
// orphaned context AND any stray agent snapshots, while preserving the context
// of sessions the user can still open from History.
export function pruneOrphanScopedKeys() {
  if (typeof window === "undefined") return;
  const keep = _historySessionIds();
  const active = storage.getItem(STORAGE_KEYS.SESSION_ID);
  if (active) keep.add(active);
  _sweepScopedKeys(
    [...SESSION_SCOPED_CONTEXT_PREFIXES, ...SESSION_SCOPED_FINDING_PREFIXES],
    [window.localStorage],
    keep,
  );
  _sweepScopedKeys(SESSION_SCOPED_TRANSIENT_PREFIXES, [window.sessionStorage], keep);
}

export function expireSessionCookie() {
  if (typeof document === "undefined") return;
  document.cookie = `${STORAGE_KEYS.SESSION_ID}=; path=/; max-age=0; SameSite=Lax`;
}

export function clearInvestigationPersistence() {
  const savedHistory = _saveHistory();

  try {
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
    pruneOrphanScopedKeys();
    expireSessionCookie();
  } finally {
    _restoreHistory(savedHistory);
  }
}
