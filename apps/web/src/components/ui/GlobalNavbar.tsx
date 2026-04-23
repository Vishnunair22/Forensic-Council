"use client";

import { useState, useCallback } from "react";
import { useRouter, usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { useSound } from "@/hooks/useSound";
import { ForensicResetOverlay } from "./ForensicResetOverlay";
import { BrandLogo } from "./BrandLogo";

export function GlobalNavbar() {
  const router = useRouter();
  const pathname = usePathname();
  const [isResetting, setIsResetting] = useState(false);
  const { playSound } = useSound();

  const handleLogoClick = useCallback(() => {
    if (typeof window === "undefined") return;

    playSound("hum");
    setIsResetting(true);

    window.dispatchEvent(new Event("fc:reset-home"));

    setTimeout(() => {
        if (pathname === "/") {
          window.scrollTo({ top: 0, behavior: "smooth" });
          setTimeout(() => {
            window.dispatchEvent(new Event("fc:reset-home"));
            setIsResetting(false);
          }, 200);
        } else {
          router.push("/", { scroll: true });
          setTimeout(() => {
            window.dispatchEvent(new Event("fc:reset-home"));
            setIsResetting(false);
          }, 200);
        }
    }, 400); 
  }, [pathname, router, playSound]);

  return (
    <nav
      aria-label="Main navigation"
      className="fixed top-6 left-6 z-[200] flex items-center px-5 py-2.5 bg-black/40 backdrop-blur-xl border border-white/5 rounded-2xl shadow-[0_4px_30px_rgba(0,0,0,0.5)] w-fit whitespace-nowrap"
    >
      <AnimatePresence>
        {isResetting && <ForensicResetOverlay />}
      </AnimatePresence>

      <button
        type="button"
        className="flex items-center gap-2.5 cursor-pointer focus-visible:outline-none group bg-transparent border-none"
        onClick={handleLogoClick}
        aria-label="Return to Forensic Council home"
        aria-current={pathname === "/" ? "page" : undefined}
      >
        <BrandLogo size="md" />
      </button>
    </nav>
  );
}

