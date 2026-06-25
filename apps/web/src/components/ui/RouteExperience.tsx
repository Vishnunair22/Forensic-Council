"use client";

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import { logApiTargetDiagnostics } from "@/lib/api/utils";

export function RouteExperience() {
  const pathname = usePathname();
  // F-H-3: track whether the latest navigation was a popstate (browser back/
  // forward). On popstate we let the browser restore the previous scroll
  // position instead of forcing scroll-to-top.
  const isPopRef = useRef(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const onPop = () => { isPopRef.current = true; };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  // F-M-9: dev-only diagnostics — gated so production bundles tree-shake it.
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (process.env.NODE_ENV !== "production") {
      logApiTargetDiagnostics();
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;

    // We no longer manually scroll to top here. Next.js App Router has built-in
    // scroll management that natively handles scrolling to the top of new pages
    // or restoring scroll position on back/forward navigation.
    // Manual window.scrollTo causes double-scrolling and stutter.
  }, [pathname]);

  return null;
}
