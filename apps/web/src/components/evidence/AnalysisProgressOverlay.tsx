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
    }
  }, [isVisible, reset]);

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[10000] flex items-center justify-center p-6 bg-black/95 backdrop-blur-2xl transition-opacity duration-700"
        >
          {/* Main Glass Card */}
          <motion.div
            initial={{ scale: 0.9, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.95, opacity: 0, y: 10 }}
            transition={{ type: "spring", damping: 25, stiffness: 300 }}
            className="bg-black/60 backdrop-blur-3xl relative w-full max-w-lg overflow-hidden rounded-[2rem] p-8 sm:p-10 shadow-[0_40px_80px_rgba(0,0,0,0.8)] flex flex-col items-center gap-10 border border-white/10 hover:border-white/20 transition-colors duration-500"
          >
            {/* Spinning Indicator (Top-aligned now for better layout with bar) */}
            <div className="relative flex-shrink-0">
              <motion.div
                className="w-12 h-12 rounded-full border-2 border-primary/20"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
              />
              <motion.div
                className="absolute inset-0 w-12 h-12 rounded-full border-t-2 border-primary shadow-[0_0_15px_rgba(var(--primary),0.4)]"
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
              />
            </div>

            {/* Text & Progress Stack */}
            <div className="flex flex-col items-center text-center w-full">
              <AnimatePresence mode="wait">
                <motion.div
                  key={message}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.3 }}
                  className="flex flex-col gap-1 mb-8"
                >
                  <span className="text-sm font-semibold text-primary/80 tracking-wide drop-shadow-sm mb-0.5">
                    {title}
                  </span>
                  <h2 className="text-white text-xl sm:text-2xl font-bold tracking-tight truncate">
                    {message}
                  </h2>
                </motion.div>
              </AnimatePresence>

              {/* NEW: Progress Bar / Loader Track */}
              <div className="w-full max-w-md h-[3px] bg-white/5 rounded-full overflow-hidden shadow-[inset_0_1px_1px_rgba(0,0,0,0.5)] relative">
                {/* NEW: Progress Fill (The moving part) */}
                <motion.div 
                  initial={{ width: "0%" }}
                  animate={{ width: "100%" }}
                  transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
                  className="h-full bg-gradient-to-r from-primary/50 via-primary to-white transition-all duration-300 ease-out shadow-[0_0_15px_rgba(var(--primary),1)] relative after:absolute after:right-0 after:top-0 after:bottom-0 after:w-4 after:bg-white after:blur-[2px]"
                />
              </div>

              {/* NEW: Loading Status Text (Data-terminal readout) */}
              <div className="flex flex-col items-center gap-3 mt-6 animate-pulse">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-medium text-white/40 tracking-wide">
                    Elapsed Time:
                  </span>
                  <span className="text-xs font-bold text-white/90 tabular-nums tracking-wide">
                    {formattedTime}
                  </span>
                </div>
              </div>
            </div>

            {/* Subtle background scan effect */}
            <div className="absolute inset-0 pointer-events-none opacity-10">
              <div className="scan-line-overlay" />
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
