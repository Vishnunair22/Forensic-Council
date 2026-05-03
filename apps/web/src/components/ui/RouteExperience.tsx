"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";

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
    if (typeof window === "undefined") return;

    const behavior = prefersReducedMotion() ? "auto" : "smooth";
    const raf = window.requestAnimationFrame(() => {
      window.scrollTo({ top: 0, left: 0, behavior });
    });

    return () => window.cancelAnimationFrame(raf);
  }, [pathname]);

  return null;
}
