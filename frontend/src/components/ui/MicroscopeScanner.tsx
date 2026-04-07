"use client";

import { motion, useScroll, useTransform, useSpring } from "framer-motion";
import { useEffect, useState } from "react";

export function MicroscopeScanner() {
  const { scrollYProgress } = useScroll();
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  // Smooth out the scroll progress for more fluid lens movement
  const smoothScroll = useSpring(scrollYProgress, {
    stiffness: 100,
    damping: 30,
    restDelta: 0.001
  });

  // Calculate lens position based on scroll
  // We'll create a "sweep" pattern: horizontal zig-zag and vertical descent
  const x = useTransform(smoothScroll, [0, 0.25, 0.5, 0.75, 1], ["5%", "95%", "5%", "95%", "5%"]);
  const y = useTransform(smoothScroll, [0, 1], ["10%", "90%"]);
  
  // Opacity fade in/out near top and bottom
  const opacity = useTransform(smoothScroll, [0, 0.05, 0.95, 1], [0, 1, 1, 0]);

  if (!isMounted) return null;

  return (
    <div className="fixed inset-0 pointer-events-none z-[150] overflow-hidden">
      {/* The Scanning Lens */}
      <motion.div
        style={{ x, y, opacity }}
        className="absolute w-40 h-40 -ml-20 -mt-20 flex items-center justify-center"
      >
        {/* Outer Glow Ring */}
        <div className="absolute inset-0 rounded-full border border-cyan-500/20 bg-cyan-500/5 blur-[2px] animate-pulse" />
        
        {/* Main Lens Circle */}
        <div className="absolute inset-2 rounded-full border-2 border-cyan-400/40 backdrop-blur-[2px] overflow-hidden bg-white/5 shadow-[0_0_30px_rgba(34,211,238,0.2)]">
          {/* Internal Crosshair */}
          <div className="absolute inset-0 flex items-center justify-center opacity-40">
             <div className="w-full h-[1px] bg-cyan-400/50" />
             <div className="h-full w-[1px] bg-cyan-400/50" />
          </div>
          
          {/* Scanning Line Sweep (Infinite Loop) */}
          <motion.div 
            animate={{ 
              top: ["0%", "100%", "0%"],
              opacity: [0.2, 0.8, 0.2]
            }}
            transition={{ 
              duration: 3, 
              repeat: Infinity, 
              ease: "easeInOut" 
            }}
            className="absolute left-0 right-0 h-[2px] bg-cyan-300 shadow-[0_0_10px_rgba(34,211,238,1)] z-10" 
          />

          {/* Micro-sweeps / Aberration Overlay */}
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_40%,rgba(34,211,238,0.05)_100%)]" />
        </div>

        {/* Decorative corner markers */}
        <div className="absolute -top-2 -left-2 w-4 h-4 border-t-2 border-l-2 border-cyan-400/60" />
        <div className="absolute -top-2 -right-2 w-4 h-4 border-t-2 border-r-2 border-cyan-400/60" />
        <div className="absolute -bottom-2 -left-2 w-4 h-4 border-b-2 border-l-2 border-cyan-400/60" />
        <div className="absolute -bottom-2 -right-2 w-4 h-4 border-b-2 border-r-2 border-cyan-400/60" />
      </motion.div>

      {/* Global Scanning Overlay (Subtle scanline pattern) */}
      <div className="absolute inset-0 opacity-[0.03] pointer-events-none bg-[linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.25)_50%),linear-gradient(90deg,rgba(255,0,0,0.06),rgba(0,255,0,0.02),rgba(0,0,255,0.06))] bg-[length:100%_4px,3px_100%]" />
    </div>
  );
}
