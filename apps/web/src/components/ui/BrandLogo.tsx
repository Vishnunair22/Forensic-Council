"use client";

import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";

interface BrandLogoProps {
  className?: string;
  size?: "sm" | "md" | "lg";
  isHovered?: boolean;
}

export function BrandLogo({ className, size = "md", isHovered = false }: BrandLogoProps) {
  const iconSizes = {
    sm: "w-9 h-9",
    md: "w-11 h-11",
    lg: "w-16 h-16",
  };

  const textSizes = {
    sm: "text-lg",
    md: "text-xl",
    lg: "text-3xl",
  };

  return (
    <div className={cn("flex items-center", size === "sm" ? "gap-3" : "gap-4", className)}>
      {/* --- Horizon Aperture Icon --- */}
      <motion.div
        className={cn(
          "relative flex items-center justify-center rounded-lg bg-black/40 border border-white/5 overflow-hidden",
          iconSizes[size]
        )}
      >

        {/* Glow effect on hover */}
        <motion.div
          animate={{ opacity: isHovered ? 0.3 : 0.1 }}
          className="absolute inset-0 bg-primary blur-xl"
        />

        {/* HUD Elements */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-20">
          <div className="w-[80%] h-[1px] bg-primary" />
          <div className="h-[80%] w-[1px] bg-primary" />
        </div>

        {/* The "FC" Core */}
        <span className="relative text-white bg-black/80 px-1 rounded-sm font-mono font-bold text-[10px] z-10 tracking-tight">
          FC
        </span>
      </motion.div>


      {/* --- Horizon Name & Reset Context --- */}
      <div className="flex flex-col justify-center">
        <div className="flex items-center gap-1.5 leading-tight">
          <span className={cn(
            "font-heading font-bold text-white tracking-wider",
            textSizes[size]
          )}>
            Forensic
          </span>
          <span className={cn(
            "font-heading font-bold text-primary drop-shadow-[0_0_15px_rgba(59,130,246,0.4)] tracking-wider",
            textSizes[size]
          )}>
            Council
          </span>
        </div>


        {/* Back To Home Hint */}
        <AnimatePresence>
          {isHovered && (
            <motion.span
              initial={{ opacity: 0, y: -3 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="text-[9px] font-mono font-bold tracking-widest text-primary/50 uppercase block leading-none mt-0.5"
            >
              ← Reset & Home
            </motion.span>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
