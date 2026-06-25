"use client";

import { useEffect, useState, useRef } from "react";
import { usePathname } from "next/navigation";
import { AnimatePresence } from "framer-motion";
import { LoadingOverlay } from "@/components/ui/LoadingOverlay";
import { storage, sessionOnlyStorage } from "@/lib/storage";
import { STORAGE_KEYS } from "@/lib/storageKeys";
import { __pendingFileStore } from "@/lib/pendingFileStore";
import { EVIDENCE_MAX_DISPLAY_MS } from "@/lib/timings";

export function GlobalLoadingOverlay() {
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);
  // Always initialise false on both server and client to avoid hydration mismatch.
  // Storage-dependent state is resolved in the mount effect below.
  const [show, setShow] = useState(false);
  const [liveText, setLiveText] = useState(() => {
    return sessionOnlyStorage.getItem(STORAGE_KEYS.FC_LOADING_TEXT) || "Opening evidence analysis...";
  });
  const [dispatchedCount, setDispatchedCount] = useState(() => {
    const stored = sessionOnlyStorage.getItem(STORAGE_KEYS.FC_LOADING_DISPATCHED);
    return stored ? parseInt(stored, 10) || 0 : 0;
  });
  const safetyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountTimeRef = useRef(Date.now());

  useEffect(() => {
    // Resolve initial show state from sessionStorage only after mount to avoid
    // server/client hydration mismatch.

    // We removed the aggressive isHardRefresh clearing here because it broke
    // normal app refreshes (F5) by clearing session storage when type === "reload".
    // Stale states are gracefully handled by FC_HARD_REFRESH_GUARD instead.

    const showLoading = sessionOnlyStorage.getItem(STORAGE_KEYS.FC_SHOW_LOADING) === "true";
    const isHandoffActive = sessionOnlyStorage.getItem(STORAGE_KEYS.FC_HANDOFF_FIRED) === "1";
    const isAutoStart = sessionOnlyStorage.getItem(STORAGE_KEYS.AUTO_START) === "true";

    if (pathname !== "/evidence") {
      if (showLoading && (isHandoffActive || isAutoStart)) {
        setShow(true);
      } else if (showLoading) {
        sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
      }
    } else if (showLoading) {
      const guard = sessionOnlyStorage.getItem(STORAGE_KEYS.FC_HARD_REFRESH_GUARD);
      if (guard) {
        const guardTime = parseInt(guard, 10);
        const pendingFile = __pendingFileStore.file;
        // Guard clears the overlay if: within 30s window AND no file in memory
        // (regardless of AUTO_START — a hard refresh kills the in-memory file).
        if (!isNaN(guardTime) && Date.now() - guardTime < 30000 && !pendingFile) {
          sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
          sessionOnlyStorage.removeItem(STORAGE_KEYS.AUTO_START);
          sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_HANDOFF_FIRED);
        } else if (pendingFile) {
          // File is still in memory (normal page reload, not hard refresh).
          setShow(true);
        } else {
          // Guard expired (>30s) with no file — clear stale state.
          sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
          sessionOnlyStorage.removeItem(STORAGE_KEYS.AUTO_START);
          sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_HANDOFF_FIRED);
        }
      } else {
        setShow(true);
      }
    }

    setMounted(true);
  }, [pathname]);

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
    // Guard: never dismiss while a handoff is actively in progress, regardless of pathname
    if (
      sessionOnlyStorage.getItem(STORAGE_KEYS.FC_HANDOFF_FIRED) === "1" &&
      sessionOnlyStorage.getItem(STORAGE_KEYS.FC_SHOW_LOADING) === "true"
    ) {
      return;
    }
    if (pathname === "/" && sessionOnlyStorage.getItem(STORAGE_KEYS.FC_SHOW_LOADING) === "true") {
      return;
    }
    if (pathname !== "/evidence") {
      dismiss();
    }
  }, [pathname]);

  useEffect(() => {
    const handleStorageUpdate = (e: Event) => {
      const { key, value } = (e as CustomEvent<{ key: string; value: string | null }>).detail;
      if (key === STORAGE_KEYS.FC_SHOW_LOADING) {
        if (value === "true") {
          mountTimeRef.current = Date.now();
          setShow(true);
        } else {
          const isGracePeriod =
            (sessionOnlyStorage.getItem(STORAGE_KEYS.FC_HANDOFF_FIRED) === "1" ||
             sessionOnlyStorage.getItem(STORAGE_KEYS.AUTO_START) === "true") &&
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

  useEffect(() => {
    if (pathname !== "/" && !pathname.startsWith("/evidence")) {
      dismiss();
      return;
    }
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
      {mounted && show && (
        <LoadingOverlay
          key="global-loading"
          liveText={liveText}
          dispatchedCount={dispatchedCount}
        />
      )}
    </AnimatePresence>
  );
}
