"use client";

import { useState, useCallback } from "react";
import { useRouter, usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { useForensicSfx } from "@/hooks/useForensicSfx";
import { ForensicResetOverlay } from "./ForensicResetOverlay";

export function GlobalNavbar() {
  const router = useRouter();
  const pathname = usePathname();
  const [isResetting, setIsResetting] = useState(false);
  const { playHum } = useForensicSfx();

  const handleLogoClick = useCallback(() => {
    if (typeof window === "undefined") return;

    // Trigger Multi-Sensory Reset
    playHum();
    setIsResetting(true);

    // Global event for local state resets
    window.dispatchEvent(new Event("fc:reset-home"));

    // Delay the landing page re-initialization to synchronize with the 'Oracle Focus' peak
    setTimeout(() => {
        if (pathname === "/") {
          window.location.reload(); 
        } else {
          router.push("/", { scroll: true });
          setTimeout(() => setIsResetting(false), 200);
        }
    }, 400); // Shorter, crisper delay
  }, [pathname, router, playHum]);

  return (
    <nav
      aria-label="Main navigation"
      className="absolute top-0 left-0 right-0 z-[200] flex items-center justify-between px-10 py-6 border-b border-white/[0.03] bg-transparent backdrop-blur-md transition-all duration-500"
    >
      <AnimatePresence>
        {isResetting && <ForensicResetOverlay />}
      </AnimatePresence>

      <button
        type="button"
        className="flex items-center gap-5 cursor-pointer focus-visible:outline-none group"
        onClick={handleLogoClick}
        aria-label="Return to Forensic Council home"
      >
        <motion.div
          className="w-12 h-12 rounded-2xl flex items-center justify-center text-sm font-black text-black shadow-[0_0_30px_rgba(20,184,166,0.2)]"
          style={{
            background: "linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%)",
          }}
          whileHover={{ scale: 1.05, rotate: 5 }}
          whileTap={{ scale: 0.95 }}
          transition={{ duration: 0.4, ease: "easeOut" }}
          aria-hidden="true"
        >
          FC
        </motion.div>

        <span className="text-[13px] font-bold uppercase tracking-[0.35em] text-white/80 group-hover:text-sky-400 transition-colors duration-200">
          Forensic Council
        </span>
      </button>

      <div className="flex items-center gap-6" />
    </nav>
  );
}
