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
          "relative flex items-center justify-center rounded-xl overflow-hidden shrink-0",
          iconSizes[size]
        )}
        animate={{
          boxShadow: isHovered
            ? "inset 0 1px 0 rgba(255,255,255,0.10), 0 0 18px rgba(79,142,247,0.30), 0 2px 12px rgba(0,0,0,0.5)"
            : "inset 0 1px 0 rgba(255,255,255,0.06), 0 0 8px rgba(79,142,247,0.12), 0 2px 12px rgba(0,0,0,0.4)",
        }}
        transition={{ duration: 0.25 }}
        style={{
          background: "linear-gradient(140deg, #0D1829 0%, #060E1A 100%)",
          border: "1px solid rgba(79,142,247,0.30)",
        }}
      >
        {/* Core glow */}
        <motion.div
          animate={{ opacity: isHovered ? 0.50 : 0.16 }}
          transition={{ duration: 0.25 }}
          className="absolute inset-0"
          style={{ background: "radial-gradient(circle at 50% 40%, rgba(79,142,247,0.9), transparent 68%)" }}
        />

        {/* Crosshair — horizontal */}
        <div
          className="absolute inset-0 flex items-center justify-center pointer-events-none"
          style={{ opacity: isHovered ? 0.45 : 0.28 }}
        >
          <div className="w-[72%] h-px" style={{ background: "linear-gradient(90deg, transparent, rgba(165,200,255,0.9) 30%, rgba(165,200,255,0.9) 70%, transparent)" }} />
        </div>
        {/* Crosshair — vertical */}
        <div
          className="absolute inset-0 flex items-center justify-center pointer-events-none"
          style={{ opacity: isHovered ? 0.45 : 0.28 }}
        >
          <div className="h-[72%] w-px" style={{ background: "linear-gradient(to bottom, transparent, rgba(165,200,255,0.9) 30%, rgba(165,200,255,0.9) 70%, transparent)" }} />
        </div>

        {/* Center dot */}
        <motion.div
          animate={{ opacity: isHovered ? 1 : 0.55 }}
          transition={{ duration: 0.2 }}
          className="absolute w-1 h-1 rounded-full"
          style={{ background: "rgba(165,200,255,0.95)", boxShadow: "0 0 6px rgba(79,142,247,0.8)" }}
        />

        {/* FC mark */}
        <span
          className="relative z-10 font-mono font-black select-none"
          style={{
            fontSize: size === "lg" ? "11px" : "9px",
            color: isHovered ? "rgba(220,235,255,1)" : "rgba(165,200,255,0.85)",
            letterSpacing: "0.06em",
            textShadow: "0 0 10px rgba(79,142,247,0.6)",
          }}
        >
          FC
        </span>
      </motion.div>

      {/* Wordmark */}
      <div className="flex flex-col justify-center leading-none">
        <div className="flex items-baseline gap-[5px]">
          <motion.span
            animate={{ color: isHovered ? "rgba(255,255,255,0.98)" : "rgba(255,255,255,0.88)" }}
            transition={{ duration: 0.2 }}
            className={cn("font-heading font-bold tracking-tight", textSizes[size])}
            style={{ letterSpacing: "-0.02em" }}
          >
            Forensic
          </motion.span>
          <motion.span
            animate={{
              textShadow: isHovered
                ? "0 0 22px rgba(79,142,247,0.7)"
                : "0 0 14px rgba(79,142,247,0.35)",
            }}
            transition={{ duration: 0.2 }}
            className={cn("font-heading font-bold tracking-tight", textSizes[size])}
            style={{ color: "var(--color-primary)", letterSpacing: "-0.02em" }}
          >
            Council
          </motion.span>
        </div>

        <AnimatePresence>
          {isHovered && (
            <motion.span
              initial={{ opacity: 0, y: -3 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -2 }}
              transition={{ duration: 0.15 }}
              className="fc-eyebrow fc-text-faint mt-0.5"
            >
              Reset & Home
            </motion.span>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
