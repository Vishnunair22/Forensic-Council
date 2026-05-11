"use client";

import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";

interface BrandLogoProps {
  className?: string;
  size?: "sm" | "md" | "lg";
  isHovered?: boolean;
}
export function BrandLogo({ className, size = "md", isHovered = false }: BrandLogoProps) {
  const iconSizes = { sm: "w-8 h-8", md: "w-10 h-10", lg: "w-14 h-14" };
  const textSizes = { sm: "text-[15px]", md: "text-[17px]", lg: "text-[28px]" };

  return (
    <div className={cn("flex items-center", size === "sm" ? "gap-2.5" : "gap-3", className)}>
      {/* Icon mark */}
      <motion.div
        className={cn(
          "relative flex items-center justify-center rounded-lg overflow-hidden shrink-0",
          iconSizes[size]
        )}
        style={{
          background: "linear-gradient(140deg, #0A1428 0%, #06101E 100%)",
          border: "1px solid rgba(165,200,255,0.12)",
          boxShadow: "inset 0 1px 0 rgba(255,255,255,0.06), 0 2px 12px rgba(0,0,0,0.4)",
        }}
      >
        {/* Glow */}
        <motion.div
          animate={{ opacity: isHovered ? 0.35 : 0.08 }}
          transition={{ duration: 0.3 }}
          className="absolute inset-0"
          style={{ background: "radial-gradient(circle, rgba(79,142,247,0.8), transparent 70%)" }}
        />

        {/* Crosshair lines */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-15">
          <div className="w-[75%] h-px" style={{ background: "rgba(165,200,255,0.8)" }} />
        </div>
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-15">
          <div className="h-[75%] w-px" style={{ background: "rgba(165,200,255,0.8)" }} />
        </div>

        {/* FC mark */}
        <span
          className="relative z-10 font-mono font-black tracking-tight select-none"
          style={{
            fontSize: size === "lg" ? "11px" : "9px",
            color: "rgba(165,200,255,0.9)",
            letterSpacing: "0.05em",
          }}
        >
          FC
        </span>
      </motion.div>

      {/* Wordmark */}
      <div className="flex flex-col justify-center leading-none">
        <div className="flex items-baseline gap-[5px]">
          <span
            className={cn("font-heading font-bold text-white/90 tracking-tight", textSizes[size])}
            style={{ letterSpacing: "-0.02em" }}
          >
            Forensic
          </span>
          <span
            className={cn("font-heading font-bold tracking-tight", textSizes[size])}
            style={{
              color: "var(--color-primary)",
              letterSpacing: "-0.02em",
              textShadow: "0 0 18px rgba(79,142,247,0.4)",
            }}
          >
            Council
          </span>
        </div>

        <AnimatePresence>
          {isHovered && (
            <motion.span
              initial={{ opacity: 0, y: -2 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.12 }}
              className="text-[8px] font-mono font-bold tracking-[0.22em] text-primary-soft/50 uppercase mt-0.5"
            >
              Reset & Home
            </motion.span>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
