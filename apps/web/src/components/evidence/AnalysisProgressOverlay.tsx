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
          className="fixed inset-0 z-[10000] flex items-center justify-center p-6 bg-black/40 backdrop-blur-3xl"
        >
          {/* Main Glass Card */}
          <motion.div
            initial={{ scale: 0.9, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.95, opacity: 0, y: 10 }}
            transition={{ type: "spring", damping: 25, stiffness: 300 }}
            className="frosted-panel relative w-full max-w-lg overflow-hidden rounded-[2rem] p-8 sm:p-10 shadow-2xl flex flex-col sm:flex-row items-center gap-8 border border-white/5"
          >
            {/* Left: Spinning Indicator */}
            <div className="relative flex-shrink-0">
              <motion.div
                className="w-16 h-16 rounded-full border-2 border-primary/20"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
              />
              <motion.div
                className="absolute inset-0 w-16 h-16 rounded-full border-t-2 border-primary shadow-[0_0_15px_rgba(34,211,238,0.4)]"
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
              />
            </div>

            {/* Right: Text Stack */}
            <div className="flex flex-col text-center sm:text-left overflow-hidden w-full">
              <AnimatePresence mode="wait">
                <motion.div
                  key={message}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  transition={{ duration: 0.3 }}
                  className="flex flex-col gap-1"
                >
                  <span className="text-[10px] font-mono font-bold text-primary/50 tracking-[0.3em]">
                    {title.toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase())}
                  </span>
                  <h2 className="text-white text-lg sm:text-xl font-bold tracking-wider font-mono truncate">
                    {message.toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase())}
                  </h2>
                </motion.div>
              </AnimatePresence>

              <motion.div 
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.4 }}
                className="mt-3 flex items-center justify-center sm:justify-start gap-2"
              >
                <span className="text-[9px] font-mono text-white/30 tracking-widest">
                  Elapsed Time:
                </span>
                <span className="text-[11px] font-mono font-bold text-white/60 tabular-nums">
                  {formattedTime}
                </span>
              </motion.div>
            </div>

            {/* Subtle background scan effect */}
            <div className="absolute inset-0 pointer-events-none opacity-20">
              <div className="scan-line-overlay" />
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
