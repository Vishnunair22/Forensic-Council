"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { AnimatePresence } from "framer-motion";
import { LoadingOverlay } from "@/components/ui/LoadingOverlay";
import { sessionOnlyStorage } from "@/lib/storage";

export function GlobalLoadingOverlay() {
  const pathname = usePathname();
  const [show, setShow] = useState(() => sessionOnlyStorage.getItem("fc_show_loading") === "true");

  useEffect(() => {
    const handleStorageUpdate = (e: Event) => {
      const { key, value } = (e as CustomEvent<{ key: string; value: string | null }>).detail;
      if (key === "fc_show_loading") {
        setShow(value === "true");
      }
    };
    window.addEventListener("fc_storage_update", handleStorageUpdate);
    return () => window.removeEventListener("fc_storage_update", handleStorageUpdate);
  }, []);

  // Hand off to the evidence page's own overlay once navigation completes
  const visible = show && pathname !== "/evidence";

  return (
    <AnimatePresence>
      {visible && <LoadingOverlay key="global-loading" liveText="Opening evidence analysis..." />}
    </AnimatePresence>
  );
}
