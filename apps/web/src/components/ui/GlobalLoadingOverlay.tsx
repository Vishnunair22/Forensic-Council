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
  const [show, setShow] = useState(() => {
    if (typeof window !== "undefined" && pathname !== "/evidence") {
      sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
      return false;
    }
    const showLoading = sessionOnlyStorage.getItem(STORAGE_KEYS.FC_SHOW_LOADING) === "true";
    if (showLoading) {
      const guard = sessionOnlyStorage.getItem(STORAGE_KEYS.FC_HARD_REFRESH_GUARD);
      if (guard) {
        const guardTime = parseInt(guard, 10);
        const isAutoStart = sessionOnlyStorage.getItem(STORAGE_KEYS.AUTO_START) === "true";
        if (!isNaN(guardTime) && Date.now() - guardTime < 30000 && !__pendingFileStore.file && !isAutoStart) {
          sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
          return false;
        }
      }
    }
    return showLoading;
  });
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
    setMounted(true);
  }, []);

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
            sessionOnlyStorage.getItem(STORAGE_KEYS.FC_HANDOFF_FIRED) === "1" &&
            !storage.getItem(STORAGE_KEYS.SESSION_ID) &&
            sessionOnlyStorage.getItem(STORAGE_KEYS.FC_SHOW_LOADING) === "true" &&
            __pendingFileStore.file !== null;
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
