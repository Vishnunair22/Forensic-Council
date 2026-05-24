"use client";

import { useEffect, useState, useRef } from "react";
import { usePathname } from "next/navigation";
import { AnimatePresence } from "framer-motion";
import { LoadingOverlay } from "@/components/ui/LoadingOverlay";
import { sessionOnlyStorage } from "@/lib/storage";
import { STORAGE_KEYS } from "@/lib/storageKeys";

// Maximum time (ms) the GlobalLoadingOverlay can stay visible on /evidence.
// useInvestigation manages its own overlay from that point — the global one
// is only a navigation-gap bridge. If the evidence page hooks don't dismiss
// it within this window (e.g. auth error / WS failure), we force-dismiss so
// the page isn't permanently covered.
const EVIDENCE_MAX_DISPLAY_MS = 8_000;

export function GlobalLoadingOverlay() {
  const [show, setShow] = useState(false);
  const [liveText, setLiveText] = useState("Opening evidence analysis...");
  const [dispatchedCount, setDispatchedCount] = useState(0);
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

  // Hydrate from sessionStorage once on mount
  useEffect(() => {
    const shouldShow = sessionOnlyStorage.getItem(STORAGE_KEYS.FC_SHOW_LOADING) === "true";
    setShow(shouldShow);
    const storedText = sessionOnlyStorage.getItem(STORAGE_KEYS.FC_LOADING_TEXT);
    if (storedText) setLiveText(storedText);
    const storedCount = sessionOnlyStorage.getItem(STORAGE_KEYS.FC_LOADING_DISPATCHED);
    if (storedCount) setDispatchedCount(parseInt(storedCount, 10) || 0);
  }, []);

  // Listen for storage updates dispatched by useInvestigation
  useEffect(() => {
    const handleStorageUpdate = (e: Event) => {
      const { key, value } = (e as CustomEvent<{ key: string; value: string | null }>).detail;
      if (key === STORAGE_KEYS.FC_SHOW_LOADING) {
        if (value === "true") {
          setShow(true);
        } else {
          // useInvestigation cleared the flag — dismiss immediately without dispatching updates back
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
      // Left the active pathways — always dismiss immediately
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
