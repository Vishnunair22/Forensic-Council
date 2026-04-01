"use client";

import { useState, useCallback } from "react";
import { useRouter, usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { HistoryDrawer } from "@/components/ui/HistoryDrawer";

export function GlobalNavbar() {
  const router = useRouter();
  const pathname = usePathname();
  const [isHovered, setIsHovered] = useState(false);

  const isHome = pathname === "/";

  const handleLogoClick = useCallback(() => {
    window.dispatchEvent(new Event("fc:reset-home"));

    if (pathname === "/") {
      const hero = document.getElementById("hero");
      if (hero) {
        hero.scrollIntoView({ behavior: "smooth", block: "start" });
      } else {
        window.scrollTo({ top: 0, behavior: "smooth" });
      }
    } else {
      router.push("/");
    }
  }, [pathname, router]);

  return (
    <nav
      aria-label="Main navigation"
      className="fixed top-0 left-0 right-0 z-[200] flex items-center justify-between px-6 py-3 border-b border-white/[0.05] bg-[#080C14]/95"
      style={{ backdropFilter: "blur(20px)" }}
    >
      <button
        type="button"
        className="flex items-center gap-3 cursor-pointer"
        onClick={handleLogoClick}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        aria-label="Return to Forensic Council home"
      >
        <motion.div
          className="w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold text-white"
          style={{ background: "linear-gradient(135deg, #0891b2 0%, #22d3ee 100%)" }}
          animate={isHovered ? {
            boxShadow: "0 0 20px rgba(34,211,238,0.5), 0 0 40px rgba(34,211,238,0.2)",
            rotate: [0, -8, 8, -4, 0],
            scale: 1.1,
          } : {
            boxShadow: "0 0 0px rgba(34,211,238,0)",
            rotate: 0,
            scale: 1,
          }}
          transition={{ duration: 0.5, ease: "easeInOut" }}
        >
          <AnimatePresence mode="wait">
            {isHovered ? (
              <motion.span
                key="expanded"
                initial={{ opacity: 0, scale: 0.5, filter: "blur(4px)" }}
                animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
                exit={{ opacity: 0, scale: 0.5, filter: "blur(4px)" }}
                transition={{ duration: 0.3 }}
              >
                FC
              </motion.span>
            ) : (
              <motion.span
                key="default"
                initial={{ opacity: 0, scale: 0.5 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.5 }}
                transition={{ duration: 0.3 }}
              >
                FC
              </motion.span>
            )}
          </AnimatePresence>
        </motion.div>

        <div className="flex flex-col items-start overflow-hidden">
          <AnimatePresence mode="wait">
            {isHovered ? (
              <motion.div
                key="expanded-name"
                className="flex flex-col items-start"
                initial={{ opacity: 0, x: -12 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -12 }}
                transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
              >
                <motion.span
                  className="text-[11px] font-bold uppercase tracking-[0.15em] text-white"
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.05, duration: 0.3 }}
                >
                  Forensic Council
                </motion.span>
                <motion.span
                  className="text-[7px] font-mono uppercase tracking-[0.3em] font-bold text-cyan-400/60 leading-tight"
                  initial={{ opacity: 0, width: 0 }}
                  animate={{ opacity: 1, width: "auto" }}
                  transition={{ delay: 0.12, duration: 0.4, ease: "easeOut" }}
                  style={{ overflow: "hidden", whiteSpace: "nowrap" }}
                >
                  Return to Home
                </motion.span>
              </motion.div>
            ) : (
              <motion.span
                key="collapsed-name"
                className="text-[11px] font-bold uppercase tracking-[0.15em] text-white/70"
                initial={{ opacity: 0, x: 12 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 12 }}
                transition={{ duration: 0.3 }}
              >
                Forensic Council
              </motion.span>
            )}
          </AnimatePresence>
        </div>
      </button>

      <div className="flex items-center gap-3">
        {!isHome && <HistoryDrawer />}
      </div>
    </nav>
  );
}
