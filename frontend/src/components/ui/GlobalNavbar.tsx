"use client";

import { useState, useCallback } from "react";
import { useRouter, usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { clsx } from "clsx";

export function GlobalNavbar() {
  const router = useRouter();
  const pathname = usePathname();
  const [isHovered, setIsHovered] = useState(false);

  const handleLogoClick = useCallback(() => {
    if (typeof window === "undefined") return;

    window.dispatchEvent(new Event("fc:reset-home"));

    if (pathname === "/") {
      const hero = document.getElementById("hero");
      if (hero) {
        hero.scrollIntoView({ behavior: "smooth", block: "start" });
      } else {
        window.scrollTo({ top: 0, behavior: "smooth" });
      }
    } else {
      router.push("/", { scroll: true });
    }
  }, [pathname, router]);

  return (
    <nav
      aria-label="Main navigation"
      className="fixed top-0 left-0 right-0 z-[200] flex items-center justify-between px-10 py-6 border-b border-white/[0.03] bg-background/40 backdrop-blur-3xl transition-all duration-500"
    >
      <button
        type="button"
        className="flex items-center gap-5 cursor-pointer focus-visible:outline-none group"
        onClick={handleLogoClick}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        aria-label="Return to Forensic Council home"
      >
        <motion.div
          className="w-12 h-12 rounded-2xl flex items-center justify-center text-sm font-black text-black shadow-[0_0_30px_rgba(34,211,238,0.2)]"
          style={{
            background: "linear-gradient(135deg, #22d3ee 0%, #0891b2 100%)",
          }}
          whileHover={{ scale: 1.05, rotate: 5 }}
          whileTap={{ scale: 0.95 }}
          transition={{ duration: 0.4, ease: "easeOut" }}
          aria-hidden="true"
        >
          FC
        </motion.div>

        <span className="text-[14px] font-black uppercase tracking-[0.4em] text-white group-hover:text-cyan-400 transition-colors duration-500">
          Forensic Council
        </span>
      </button>

      <div className="flex items-center gap-6">
        {/* Navigation could go here later */}
      </div>
    </nav>
  );
}
