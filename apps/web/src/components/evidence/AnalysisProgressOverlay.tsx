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
          className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/90 backdrop-blur-2xl"
        >
          <div className="max-w-xl w-full px-6">
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
              className="relative flex flex-col items-center text-center"
            >
              {/* Main Visuals */}
              <motion.div 
                animate={{ rotate: 360 }}
                transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
                className="w-24 h-24 border-t-2 border-r-2 border-primary rounded-full mb-12 shadow-[0_0_30px_rgba(0,255,65,0.2)]"
              />
              
              <h2 className="text-4xl font-black text-white tracking-tight mb-4">
                {title}
              </h2>
              
              <p className="text-lg font-medium text-white/40 tracking-wide max-w-sm mb-12">
                {message}
              </p>

              {/* Progress Bar */}
              <div className="w-full max-w-md h-[3px] bg-white/5 rounded-full overflow-hidden relative mb-8">
                <motion.div 
                  initial={{ width: "0%" }}
                  animate={{ width: "100%" }}
                  transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
                  className="h-full bg-primary shadow-[0_0_15px_rgba(0,255,65,0.6)]"
                />
              </div>

              {/* Timer */}
              <div className="flex items-center gap-2 text-white/50 font-mono text-xs tracking-wide">
                <span>Elapsed Time</span>
                <span className="text-white font-bold">{formattedTime}</span>
              </div>
            </motion.div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
