"use client";

import { useState, useCallback } from "react";
import { useRouter, usePathname } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { useSound } from "@/hooks/useSound";
import { ForensicResetOverlay } from "./ForensicResetOverlay";
import { BrandLogo } from "./BrandLogo";

export function GlobalNavbar() {
  const router = useRouter();
  const pathname = usePathname();
  const [isResetting, setIsResetting] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
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
      className="fixed top-8 left-8 z-[500]"
    >
      <AnimatePresence>
        {isResetting && <ForensicResetOverlay />}
      </AnimatePresence>

      <motion.button
        type="button"
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        className="horizon-glass flex items-center px-6 py-4 rounded-xl border border-white/10 group cursor-pointer transition-all duration-300 hover:border-primary/40 shadow-[0_20px_50px_rgba(0,0,0,0.5)] relative overflow-hidden"
        onClick={handleLogoClick}
        aria-label="Return to Forensic Council home"
        aria-current={pathname === "/" ? "page" : undefined}
      >
        {/* Subtle Highlight Beam */}
        <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/5 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-1000" />
        
        <BrandLogo size="sm" isHovered={isHovered} />
      </motion.button>
    </nav>
  );
}
