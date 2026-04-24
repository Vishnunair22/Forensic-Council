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
          "relative flex items-center justify-center rounded-xl bg-slate-900 border border-white/10 overflow-hidden",
          iconSizes[size]
        )}
      >
        {/* Glow effect on hover */}
        <motion.div 
          animate={{ opacity: isHovered ? 0.3 : 0.1 }}
          className="absolute inset-0 bg-primary blur-xl" 
        />
        
        {/* Technical HUD Crosshair */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-[70%] h-[1px] bg-primary/30" />
          <div className="h-[70%] w-[1px] bg-primary/30" />
          <div className="absolute w-[50%] h-[50%] border border-primary/20 rounded-full" />
        </div>

        {/* The "FC" Core */}
        <span className="relative text-white font-mono font-bold text-xs z-10">
          FC
        </span>

        {/* Rotating Tick Marks (Horizon Signature) */}
        <motion.div 
          animate={{ rotate: 360 }}
          transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
          className="absolute inset-0 flex items-center justify-center"
        >
          <div className="absolute top-1 w-1 h-1 bg-primary/60 rounded-full" />
          <div className="absolute bottom-1 w-1 h-1 bg-primary/60 rounded-full" />
          <div className="absolute left-1 w-1 h-1 bg-primary/60 rounded-full" />
          <div className="absolute right-1 w-1 h-1 bg-primary/60 rounded-full" />
        </motion.div>
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
            "font-heading font-bold text-primary drop-shadow-[0_0_15px_rgba(0,255,255,0.4)] tracking-wider",
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
