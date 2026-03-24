"use client";

import React from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface CyberNoirPanelProps extends React.ComponentPropsWithoutRef<typeof motion.div> {
  children: React.ReactNode;
  className?: string;
  glow?: "cyan" | "violet" | "emerald" | "amber" | "red" | "none";
  intensity?: "low" | "medium" | "high";
  showEntrance?: boolean;
}

export function CyberNoirPanel({
  children,
  className,
  glow = "none",
  intensity = "medium",
  showEntrance = true,
  ...props
}: CyberNoirPanelProps) {
  const glowColors = {
    cyan: "rgba(0, 212, 255, 0.2)",
    violet: "rgba(124, 58, 237, 0.25)",
    emerald: "rgba(16, 185, 129, 0.15)",
    amber: "rgba(245, 158, 11, 0.15)",
    red: "rgba(239, 68, 68, 0.2)",
    none: "transparent",
  };

  const intensityMap = {
    low: 0.1,
    medium: 0.25,
    high: 0.5,
  };

  const selectedGlow = glowColors[glow];
  const alpha = intensityMap[intensity];

  return (
    <motion.div
      initial={showEntrance ? { opacity: 0, y: 10 } : props.initial || false}
      animate={showEntrance ? { opacity: 1, y: 0 } : props.animate || false}
      transition={{ duration: 0.4, ease: "easeOut", ...props.transition }}
      {...props}
      className={cn(
        "glass-panel relative group",
        glow !== "none" && "border-opacity-40",
        className
      )}
      style={{
        boxShadow: glow !== "none" 
          ? `0 10px 40px -10px ${selectedGlow.replace("0.2", "0.1")}, inset 0 1px 0 rgba(255, 255, 255, 0.05)` 
          : undefined,
        borderColor: glow !== "none" ? selectedGlow.replace("0.2", "0.4") : undefined,
      }}
    >
      {/* Ambient background glow inside the panel */}
      {glow !== "none" && (
        <div 
          className="absolute inset-0 pointer-events-none -z-10"
          style={{
            background: `radial-gradient(circle at top left, ${selectedGlow.replace("0.2", alpha.toString())}, transparent 70%)`
          }}
        />
      )}
      
      {/* Content */}
      <div className="relative z-10">
        {children}
      </div>

      {/* Shine effect on hover */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden rounded-inherit">
        <motion.div 
          className="absolute inset-0 w-1/2 bg-gradient-to-r from-transparent via-white/5 to-transparent -skew-x-12 -translate-x-full group-hover:animate-[glass-shimmer-in_0.8s_ease-in-out]"
        />
      </div>
    </motion.div>
  );
}
