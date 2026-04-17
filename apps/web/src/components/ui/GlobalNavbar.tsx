"use client";

import { useState, useCallback } from "react";
import { useRouter, usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { useSound } from "@/hooks/useSound";
import { ForensicResetOverlay } from "./ForensicResetOverlay";

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
          window.location.reload(); 
        } else {
          router.push("/", { scroll: true });
          setTimeout(() => setIsResetting(false), 200);
        }
    }, 400); 
  }, [pathname, router, playSound]);

  return (
    <nav
      aria-label="Main navigation"
      className="sticky top-0 left-0 right-0 z-[200] flex items-center justify-between px-10 py-6 transition-all duration-500 bg-black/60 backdrop-blur-xl border-b border-white/[0.03]"
    >
      <AnimatePresence>
        {isResetting && <ForensicResetOverlay />}
      </AnimatePresence>

      <button
        type="button"
        className="flex items-center gap-4 cursor-pointer focus-visible:outline-none group bg-transparent border-none"
        onClick={handleLogoClick}
        aria-label="Return to Forensic Council home"
        aria-current={pathname === "/" ? "page" : undefined}
      >
        <motion.div
          className="w-10 h-10 rounded-xl flex items-center justify-center text-[11px] font-black text-black shadow-[0_0_20px_rgba(6,182,212,0.1)] ring-1 ring-white/5"
          style={{
            background: "linear-gradient(135deg, #0891b2 0%, #06b6d4 100%)",
          }}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
          aria-hidden="true"
        >
          FC
        </motion.div>

        <span className="text-[12px] font-bold tracking-widest text-white/40 group-hover:text-cyan-400 transition-colors duration-300">
          Forensic Council
        </span>
      </button>


    </nav>
  );
}
