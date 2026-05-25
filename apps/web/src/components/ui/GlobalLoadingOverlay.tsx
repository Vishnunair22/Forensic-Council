"use client";

import { useEffect, useState, useRef } from "react";
import { usePathname } from "next/navigation";
import { AnimatePresence } from "framer-motion";
import { LoadingOverlay } from "@/components/ui/LoadingOverlay";
import { storage, sessionOnlyStorage } from "@/lib/storage";
import { STORAGE_KEYS } from "@/lib/storageKeys";

// Maximum time (ms) the GlobalLoadingOverlay can stay visible on /evidence.
// useInvestigation manages its own overlay from that point — the global one
// is only a navigation-gap bridge. If the evidence page hooks don't dismiss
// it within this window (e.g. auth error / WS failure), we force-dismiss so
// the page isn't permanently covered.
const EVIDENCE_MAX_DISPLAY_MS = 5_000;

export function GlobalLoadingOverlay() {
  const pathname = usePathname();
  const [show, setShow] = useState(() => {
    if (typeof window !== "undefined" && pathname !== "/evidence") {
      sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
      return false;
    }
    return sessionOnlyStorage.getItem(STORAGE_KEYS.FC_SHOW_LOADING) === "true";
  });
  const [liveText, setLiveText] = useState(() => {
    const stored = sessionOnlyStorage.getItem(STORAGE_KEYS.FC_LOADING_TEXT);
    return stored || "Opening evidence analysis...";
  });
  const [dispatchedCount, setDispatchedCount] = useState(() => {
    const stored = sessionOnlyStorage.getItem(STORAGE_KEYS.FC_LOADING_DISPATCHED);
    return stored ? parseInt(stored, 10) || 0 : 0;
  });
  const safetyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountTimeRef = useRef(Date.now());

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

  useEffect(() => {
    if (pathname !== "/evidence") {
      dismiss();
    }
  }, [pathname]);

  // Listen for storage updates dispatched by useInvestigation
  useEffect(() => {
    const handleStorageUpdate = (e: Event) => {
      const { key, value } = (e as CustomEvent<{ key: string; value: string | null }>).detail;
      if (key === STORAGE_KEYS.FC_SHOW_LOADING) {
        if (value === "true") {
          setShow(true);
        } else {
          // Grace guard: block dismissal only during the narrow handoff window
          // (FC_SHOW_LOADING is still "true" in sessionStorage, meaning
          // useInvestigation hasn't explicitly requested dismissal yet).
          // Once useInvestigation calls removeItem(FC_SHOW_LOADING), that IS
          // an intentional dismiss — always honour it, even if SESSION_ID
          // isn't set yet (e.g. upload failed, auth failed, WS failed).
          const isGracePeriod =
            sessionOnlyStorage.getItem(STORAGE_KEYS.FC_HANDOFF_FIRED) === "1" &&
            !storage.getItem(STORAGE_KEYS.SESSION_ID) &&
            sessionOnlyStorage.getItem(STORAGE_KEYS.FC_SHOW_LOADING) === "true";
          if (isGracePeriod) return;
          dismiss(false);
        }
      } else if (key === STORAGE_KEYS.FC_LOADING_TEXT) {
        setLiveText(value || "Opening evidence analysis...");
      } else if (key === STORAGE_KEYS.FC_LOADING_DISPATCHED) {
        setDispatchedCount(value ? parseInt(value, 10) || 0 : 0);
      }
    };
    window.addEventListener("fc_storage_update", handleStorageUpdate);
    return () => window.removeEventListener("fc_storage_update", handleStorageUpdate);
  }, []);

  // Route-change dismissal logic
  useEffect(() => {
    if (pathname !== "/" && !pathname.startsWith("/evidence")) {
      dismiss();
      return;
    }

    // We ARE on /evidence. The overlay is a navigation-gap bridge only.
    // Start a hard safety timer: if useInvestigation hasn't dismissed it
    // within EVIDENCE_MAX_DISPLAY_MS, force-dismiss so the page is visible.
    if (show) {
      if (safetyTimerRef.current) clearTimeout(safetyTimerRef.current);
      const elapsed = Date.now() - mountTimeRef.current;
      const remaining = Math.max(0, EVIDENCE_MAX_DISPLAY_MS - elapsed);
      safetyTimerRef.current = setTimeout(() => {
        dismiss();
      }, remaining);
    }

    return () => {
      if (safetyTimerRef.current) {
        clearTimeout(safetyTimerRef.current);
        safetyTimerRef.current = null;
      }
    };
  }, [pathname, show]);

  return (
    <AnimatePresence>
      {show && (
        <LoadingOverlay
          key="global-loading"
          liveText={liveText}
          dispatchedCount={dispatchedCount}
        />
      )}
    </AnimatePresence>
  );
}
