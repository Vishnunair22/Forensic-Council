"use client";

import { motion } from "framer-motion";

/**
 * GlobalFooter: Universal footer for the Horizon theme.
 * Keeps original disclaimer text while adding forensic telemetry styling.
 */
export function GlobalFooter() {
  return (
    <footer className="w-full py-12 px-8 relative z-[100] border-t border-primary/10 bg-surface-1 backdrop-blur-md mt-auto overflow-hidden">
      {/* Decorative Scan Line on the border */}
      <motion.div 
        animate={{ x: ["-100%", "100%"] }}
        transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
        className="absolute top-0 left-0 w-1/3 h-[1px] bg-gradient-to-r from-transparent via-primary/40 to-transparent"
      />

      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-6">
        {/* Left Telemetry */}
        <div className="hidden md:block text-[9px] font-mono tracking-[0.3em] text-primary/30">
          [ SYSTEM_DISCLAIMER_ALPHA ]
        </div>

        {/* The Mandatory Text (Untouched) */}
        <p className="text-sm font-medium text-white/40 text-center max-w-xl leading-relaxed tracking-tight">
          Forensic Council is an academic project and can occasionally make mistakes.
        </p>

        {/* Right Telemetry */}
        <div className="hidden md:block text-[9px] font-mono tracking-[0.3em] text-primary/30">
          FC_VER_2.0.4 // REG: HQ
        </div>
      </div>

      {/* Subtle Bottom Glow */}
      <div className="absolute -bottom-20 left-1/2 -translate-x-1/2 w-[600px] h-32 bg-primary/5 blur-[100px] rounded-full pointer-events-none" />
    </footer>
  );
}
