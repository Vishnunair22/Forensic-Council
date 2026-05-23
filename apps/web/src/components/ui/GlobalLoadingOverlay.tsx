"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { AnimatePresence } from "framer-motion";
import { LoadingOverlay } from "@/components/ui/LoadingOverlay";
import { sessionOnlyStorage } from "@/lib/storage";
import { STORAGE_KEYS } from "@/lib/storageKeys";

export function GlobalLoadingOverlay() {
  const [show, setShow] = useState(false);
  const [liveText, setLiveText] = useState("Opening evidence analysis...");
  const [dispatchedCount, setDispatchedCount] = useState(0);
  const pathname = usePathname();

  // Hydrate from sessionStorage once on mount
  useEffect(() => {
    setShow(sessionOnlyStorage.getItem(STORAGE_KEYS.FC_SHOW_LOADING) === "true");
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
        setShow(value === "true");
      } else if (key === STORAGE_KEYS.FC_LOADING_TEXT) {
        setLiveText(value || "Opening evidence analysis...");
      } else if (key === STORAGE_KEYS.FC_LOADING_DISPATCHED) {
        setDispatchedCount(value ? parseInt(value, 10) || 0 : 0);
      }
    };
    window.addEventListener("fc_storage_update", handleStorageUpdate);
    return () => window.removeEventListener("fc_storage_update", handleStorageUpdate);
  }, []);

  // Dismiss the overlay whenever the route changes away from /evidence.
  // This is the primary safety net: if EvidenceUploadClient's unmount cleanup
  // fires AFTER this component re-renders for the new route, we still clear it.
  useEffect(() => {
    if (!pathname.startsWith("/evidence")) {
      setShow(false);
      // Also scrub the storage value to prevent re-hydrating on a remount.
      sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
      sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_LOADING_TEXT);
      sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_LOADING_DISPATCHED);
    }
  }, [pathname]);

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
