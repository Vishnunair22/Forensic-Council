"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { logApiTargetDiagnostics } from "@/lib/api/utils";

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !("matchMedia" in window)) return true;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function RouteExperience() {
  const pathname = usePathname();

  useEffect(() => {
    if (typeof window === "undefined") return;

    const previous = window.history.scrollRestoration;
    window.history.scrollRestoration = "manual";

    return () => {
      window.history.scrollRestoration = previous;
    };
  }, []);

  useEffect(() => {
    if (typeof document === "undefined") return;

    if (!pathname.startsWith("/result")) {
      document.body.removeAttribute("data-fc-loading");
    }
  }, [pathname]);

  // Dev-only diagnostics — print once per page load, not per route change.
  useEffect(() => {
    if (typeof window === "undefined") return;
    logApiTargetDiagnostics();
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;

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
