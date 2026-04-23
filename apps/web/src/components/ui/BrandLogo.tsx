"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface BrandLogoProps {
  className?: string;
  size?: "sm" | "md" | "lg";
  isHero?: boolean;
}

export function BrandLogo({ className, size = "md", isHero = false }: BrandLogoProps) {
  const iconSizes = {
    sm: "w-8 h-8",
    md: "w-10 h-10",
    lg: "w-14 h-14",
  };

  const textSizes = {
    sm: "text-lg",
    md: "text-[1.35rem]",
    lg: "text-3xl",
  };

  return (
    <div className={cn("flex items-center gap-3", className)}>
      <motion.div
        className={cn(
          "relative flex items-center justify-center rounded-2xl bg-gradient-to-b from-white/20 to-white/5 p-[1px] shadow-lg overflow-hidden group-hover:shadow-[0_0_30px_rgba(var(--primary),0.3)] transition-all duration-500 ease-out",
          iconSizes[size]
        )}
      >
        <div className="absolute inset-0 bg-black/90 backdrop-blur-xl rounded-[15px]" />
        
        {/* Technical crosshair/target effect */}
        <div className="absolute inset-0 flex items-center justify-center opacity-30">
          <div className="w-[80%] h-[1px] bg-primary/40" />
          <div className="h-[80%] w-[1px] bg-primary/40" />
          <div className="absolute w-[60%] h-[60%] border border-primary/20 rounded-full" />
        </div>

        <span className="relative text-white font-mono font-black text-sm tracking-wide z-10 group-hover:text-primary transition-colors duration-300">
          FC
        </span>

        {/* Scanning beam effect */}
        <motion.div 
          className="absolute inset-0 bg-gradient-to-b from-transparent via-primary/10 to-transparent w-full h-[200%] -top-full"
          animate={{ top: ["-100%", "100%"] }}
          transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
        />
      </motion.div>

      <div className="flex flex-col">
        <div className="flex items-center gap-1.5">
          <span className={cn(
            "font-extrabold tracking-tight text-white/90 group-hover:text-white transition-colors duration-300",
            textSizes[size]
          )}>
            Forensic
          </span>
          <span className={cn(
            "font-extrabold tracking-tight text-transparent bg-clip-text bg-gradient-to-br from-primary via-primary/80 to-primary/60 drop-shadow-[0_0_15px_rgba(var(--primary),0.3)] transition-all duration-300",
            textSizes[size]
          )}>
            Council
          </span>
        </div>
        {isHero && (
          <motion.div 
            initial={{ opacity: 0, x: -5 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.5 }}
            className="flex items-center gap-2 mt-0.5"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
            <span className="text-[10px] font-mono font-bold tracking-[0.15em] text-white/40">
              Neural Forensic Protocol v4.0
            </span>
          </motion.div>
        )}
      </div>
    </div>
  );
}
