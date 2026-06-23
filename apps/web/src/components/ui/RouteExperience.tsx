"use client";

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import { logApiTargetDiagnostics } from "@/lib/api/utils";

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !("matchMedia" in window)) return true;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

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

    // Skip forced scroll-to-top on browser back/forward so the previous scroll
    // position is preserved (e.g. returning from a History entry).
    // Always reset the flag so a same-path popstate doesn't leave it stuck true.
    const wasPop = isPopRef.current;
    isPopRef.current = false;
    if (wasPop) return;

    const behavior =
      pathname === "/evidence" || pathname.startsWith("/result")
        ? "auto"
        : prefersReducedMotion()
          ? "auto"
          : "smooth";
    const raf = window.requestAnimationFrame(() => {
      window.scrollTo({ top: 0, left: 0, behavior });
    });

    return () => window.cancelAnimationFrame(raf);
  }, [pathname]);

  return null;
}
