"use client";

import { useEffect, useState, useRef } from "react";
import { usePathname } from "next/navigation";
import { AnimatePresence } from "framer-motion";
import { LoadingOverlay } from "@/components/ui/LoadingOverlay";
import { ArbiterDeliberationOverlay } from "@/components/evidence/ArbiterDeliberationOverlay";
import { storage, sessionOnlyStorage } from "@/lib/storage";
import { STORAGE_KEYS } from "@/lib/storageKeys";

// Maximum time (ms) the GlobalLoadingOverlay can stay visible on /evidence.
// useInvestigation manages its own overlay from that point — the global one
// is only a navigation-gap bridge. If the evidence page hooks don't dismiss
// it within this window (e.g. auth error / WS failure), we force-dismiss so
// the page isn't permanently covered.
const EVIDENCE_MAX_DISPLAY_MS = 8_000;

export function GlobalLoadingOverlay() {
  const [show, setShow] = useState(() => sessionOnlyStorage.getItem(STORAGE_KEYS.FC_SHOW_LOADING) === "true");
  const [liveText, setLiveText] = useState(() => {
    const stored = sessionOnlyStorage.getItem(STORAGE_KEYS.FC_LOADING_TEXT);
    return stored || "Opening evidence analysis...";
  });
  const [dispatchedCount, setDispatchedCount] = useState(() => {
    const stored = sessionOnlyStorage.getItem(STORAGE_KEYS.FC_LOADING_DISPATCHED);
    return stored ? parseInt(stored, 10) || 0 : 0;
  });
  const [arbiterTransition, setArbiterTransition] = useState(() =>
    sessionOnlyStorage.getItem(STORAGE_KEYS.FC_ARBITER_TRANSITIONING) === "1"
  );
  const pathname = usePathname();
  const safetyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const dismiss = (clearStorage = true) => {
    setShow(false);
    if (clearStorage) {
      sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
      sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_LOADING_TEXT);
      sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_LOADING_DISPATCHED);
    }
    if (safetyTimerRef.current) {
      clearTimeout(safetyTimerRef.current);
      safetyTimerRef.current = null;
    }
  };

  // Listen for storage updates dispatched by useInvestigation
  useEffect(() => {
    const handleStorageUpdate = (e: Event) => {
      const { key, value } = (e as CustomEvent<{ key: string; value: string | null }>).detail;
      if (key === STORAGE_KEYS.FC_SHOW_LOADING) {
        if (value === "true") {
          setShow(true);
        } else {
          // Grace guard: during handoff (home→evidence), transient dismiss events
          // from resetSimulation or clearInvestigationPersistence should be ignored.
          // Only the explicit useInvestigation overlay-dismissal effect (triggered by
          // analysisStreamReady) and safety timers should hide the overlay.
          const isMidHandoff =
            sessionOnlyStorage.getItem(STORAGE_KEYS.FC_HANDOFF_FIRED) === "1" &&
            !storage.getItem(STORAGE_KEYS.SESSION_ID);
          if (isMidHandoff) return;
          dismiss(false);
        }
      } else if (key === STORAGE_KEYS.FC_LOADING_TEXT) {
        setLiveText(value || "Opening evidence analysis...");
      } else if (key === STORAGE_KEYS.FC_LOADING_DISPATCHED) {
        setDispatchedCount(value ? parseInt(value, 10) || 0 : 0);
      } else if (key === STORAGE_KEYS.FC_ARBITER_TRANSITIONING) {
        setArbiterTransition(value === "1");
      }
    };
    window.addEventListener("fc_storage_update", handleStorageUpdate);
    return () => window.removeEventListener("fc_storage_update", handleStorageUpdate);
  }, []);

  // Route-change dismissal logic
  useEffect(() => {
    if (pathname !== "/" && !pathname.startsWith("/evidence")) {
      // Left the active pathways — dismiss evidence loading overlay,
      // but don't dismiss arbiter transition overlay (handled by useResult)
      dismiss();
      return;
    }

    // We ARE on /evidence. The overlay is a navigation-gap bridge only.
    // Start a hard safety timer: if useInvestigation hasn't dismissed it
    // within EVIDENCE_MAX_DISPLAY_MS, force-dismiss so the page is visible.
    if (show) {
      if (safetyTimerRef.current) clearTimeout(safetyTimerRef.current);
      safetyTimerRef.current = setTimeout(() => {
        dismiss();
      }, EVIDENCE_MAX_DISPLAY_MS);
    }

    return () => {
      if (safetyTimerRef.current) {
        clearTimeout(safetyTimerRef.current);
        safetyTimerRef.current = null;
      }
    };
  }, [pathname, show]);

  return (
    <>
      <AnimatePresence>
        {show && !arbiterTransition && (
          <LoadingOverlay
            key="global-loading"
            liveText={liveText}
            dispatchedCount={dispatchedCount}
          />
        )}
      </AnimatePresence>
      <ArbiterDeliberationOverlay
        isVisible={arbiterTransition}
        liveText="Report confirmed ready. Loading result page..."
      />
    </>
  );
}
