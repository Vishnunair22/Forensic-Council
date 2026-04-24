"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useEffect } from "react";
import { useTimer } from "@/hooks/useTimer";

interface AnalysisProgressOverlayProps {
  isVisible: boolean;
  title?: string;
  message?: string;
  onComplete?: () => void;
}

export function AnalysisProgressOverlay({ 
  isVisible, 
  title = "Neural Uplink Active",
  message = "Establishing Secure Multi-Agent Bridge",
  onComplete: _onComplete 
}: AnalysisProgressOverlayProps) {
  const { formattedTime, reset } = useTimer(isVisible);

  useEffect(() => {
    if (!isVisible) {
      reset();
    } else {
      // Lock scroll when visible
      const originalOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = originalOverflow || "unset";
      };
    }
  }, [isVisible, reset]);

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[10000] flex items-center justify-center bg-slate-950/90 backdrop-blur-3xl"
        >
          <div className="max-w-xl w-full px-6">
            <motion.div
              initial={{ opacity: 0, scale: 0.98, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.98, y: 10 }}
              transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
              className="relative flex flex-col items-center text-center"
            >
              {/* --- Horizon Aperture Loader --- */}
              <div className="relative w-24 h-24 mb-12 flex items-center justify-center">
                <motion.div 
                  animate={{ rotate: 360 }}
                  transition={{ duration: 8, repeat: Infinity, ease: "linear" }}
                  className="absolute inset-0 rounded-full border border-primary/20 border-dashed"
                />
                <motion.div 
                  animate={{ rotate: -360 }}
                  transition={{ duration: 12, repeat: Infinity, ease: "linear" }}
                  className="absolute inset-4 rounded-full border border-primary/10 border-dashed"
                />
                <div className="w-2 h-2 rounded-full bg-primary animate-pulse shadow-[0_0_15px_rgba(0,255,255,0.8)]" />
              </div>
              
              <h2 className="text-3xl md:text-4xl font-heading font-bold text-white tracking-tight mb-4">
                {title}
              </h2>
              
              <p className="text-base font-medium text-white/40 tracking-wide max-w-sm mb-12">
                {message}
              </p>

              {/* Horizon Progress Bar */}
              <div className="w-full max-w-xs h-[2px] bg-white/5 rounded-full overflow-hidden relative mb-8">
                <motion.div 
                  initial={{ x: "-100%" }}
                  animate={{ x: "100%" }}
                  transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
                  className="absolute top-0 bottom-0 w-1/2 bg-gradient-to-r from-transparent via-primary to-transparent"
                />
              </div>

              {/* Timer HUD */}
              <div className="flex items-center gap-3 text-[10px] font-mono tracking-[0.2em] text-white/30">
                <span className="uppercase">Elapsed_Time</span>
                <span className="text-primary font-bold">{formattedTime}</span>
              </div>
            </motion.div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
