"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useEffect } from "react";
import { Loader2 } from "lucide-react";

interface AnalysisProgressOverlayProps {
  isVisible: boolean;
  title?: string;
  message?: string;
}

export function AnalysisProgressOverlay({ 
  isVisible, 
  title = "Initializing",
  message = "Please wait...",
}: AnalysisProgressOverlayProps) {

  useEffect(() => {
    if (isVisible) {
      const originalOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = originalOverflow || "unset";
      };
    }
  }, [isVisible]);

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/80 backdrop-blur-md"
        >
          <div className="max-w-md w-full px-6 flex flex-col items-center text-center">
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ duration: 0.3 }}
              className="flex flex-col items-center"
            >
              <Loader2 className="w-10 h-10 text-primary animate-spin mb-6" />
              
              <h2 className="text-2xl font-bold text-white mb-2 tracking-tight">
                {title}
              </h2>
              
              <p className="text-zinc-400 text-sm font-medium">
                {message}
              </p>
            </motion.div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
