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
    <div className={cn("flex items-center gap-4", className)}>
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
          className="absolute inset-0 bg-[var(--color-success-light)] blur-xl" 
        />
        
        {/* HUD Elements */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-20">
          <div className="w-[80%] h-[1px] bg-[var(--color-success-light)]" />
          <div className="h-[80%] w-[1px] bg-[var(--color-success-light)]" />
        </div>

        {/* The "FC" Core */}
        <span className="relative text-white font-mono font-bold text-[10px] z-10 tracking-tight">
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
            "font-heading font-bold text-[var(--color-success-light)] drop-shadow-[0_0_15px_rgba(167,255,210,0.4)] tracking-wider",
            textSizes[size]
          )}>
            Council
          </span>
        </div>


        {/* Back To Home Hint */}
        <AnimatePresence mode="wait">
          {isHovered && (
            <motion.div
              initial={{ opacity: 0, y: -5 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -5 }}
              transition={{ duration: 0.2 }}
              className="absolute mt-10"
            >
              <span className="text-[10px] font-mono font-bold tracking-widest text-primary/60 uppercase">
                Back To Home
              </span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
