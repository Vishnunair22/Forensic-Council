"use client";

import { useState, useCallback } from "react";
import { useRouter, usePathname } from "next/navigation";
import { motion } from "framer-motion";

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
          style={{
            background: "linear-gradient(135deg, #0891b2 0%, #22d3ee 100%)",
          }}
          animate={
            isHovered
              ? { scale: [1, 1.08, 1], rotate: [0, -3, 3, 0] }
              : { scale: 1, rotate: 0 }
          }
          transition={{ duration: 0.4, ease: "easeOut" }}
          aria-hidden="true"
        >
          FC
        </motion.div>

        <div className="flex flex-col items-start overflow-hidden">
          <span className="text-[14px] font-bold uppercase tracking-[0.15em] text-white">
            Forensic Council
          </span>
        </div>
      </button>

      {/* Navbar empty on the right as per "nothing else" requirement */}
      <div className="flex items-center gap-3" />
    </nav>
  );
}
