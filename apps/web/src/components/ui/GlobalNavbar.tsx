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
      className="absolute top-6 left-6 z-[200] flex items-center px-5 py-2.5 bg-black/40 backdrop-blur-xl border border-white/5 rounded-2xl shadow-[0_4px_30px_rgba(0,0,0,0.5)] w-fit whitespace-nowrap"
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
        <motion.div
          className="relative w-10 h-10 flex items-center justify-center rounded-xl bg-gradient-to-br from-primary/80 to-black p-[1px] shadow-[0_0_15px_rgba(var(--primary),0.15)] group-hover:shadow-[0_0_25px_rgba(var(--primary),0.3)] transition-all duration-700 ease-out"
          whileHover={{ scale: 1.02, rotate: -2 }}
          whileTap={{ scale: 0.98 }}
        >
          <div className="w-full h-full bg-black rounded-[11px] flex items-center justify-center overflow-hidden relative">
            <span className="text-primary font-mono font-black text-sm tracking-tighter z-10">FC</span>
            <motion.div 
               className="absolute inset-0 bg-primary/10"
               animate={{ opacity: [0.1, 0.3, 0.1] }}
               transition={{ duration: 2, repeat: Infinity }}
            />
          </div>
          
          {/* Animated Glow Ring */}
          <motion.div 
            className="absolute -inset-1 border border-primary/20 rounded-2xl"
            animate={{ scale: [1, 1.05, 1], opacity: [0.2, 0.4, 0.2] }}
            transition={{ duration: 4, ease: "easeInOut", repeat: Infinity }}
          />
        </motion.div>

        <div className="flex items-center gap-2">
          <span className="text-xl font-bold tracking-tighter text-white/90 group-hover:text-white transition-colors duration-300">
            Forensic
          </span>
          <span className="text-xl font-bold tracking-tighter text-primary group-hover:text-glow-green transition-all duration-300">
            Council
          </span>
        </div>
      </button>


    </nav>
  );
}
