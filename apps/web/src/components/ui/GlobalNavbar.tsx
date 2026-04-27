"use client";

import { useState, useCallback } from "react";
import { useRouter, usePathname } from "next/navigation";
import { AnimatePresence } from "framer-motion";
import { useSound } from "@/hooks/useSound";
import { ForensicResetOverlay } from "./ForensicResetOverlay";
import { BrandLogo } from "./BrandLogo";

export function GlobalNavbar() {
  const router = useRouter();
  const pathname = usePathname();
  const { playSound } = useSound();

  const handleLogoClick = useCallback(() => {
    if (typeof window === "undefined") return;

    playSound("hum");
    window.dispatchEvent(new Event("fc:reset-home"));

    if (pathname === "/") {
      window.scrollTo({ top: 0, behavior: "smooth" });
    } else {
      router.push("/", { scroll: true });
    }
  }, [pathname, router, playSound]);

  return (
    <nav
      aria-label="Main navigation"
      className="fixed top-8 left-8 z-[500]"
    >
      <button
        type="button"
        className="flex items-center px-5 py-3 bg-surface-2 rounded-full border border-white/10 shadow-2xl hover:bg-surface-3 transition-all active:scale-95"
        onClick={handleLogoClick}
        aria-label="Return to Forensic Council home"
        aria-current={pathname === "/" ? "page" : undefined}
      >
        <BrandLogo size="sm" isHovered={false} />
      </button>

    </nav>
  );
}

