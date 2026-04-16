"use client";

import { AlertCircle, RotateCcw, X } from "lucide-react";
import { motion } from "framer-motion";

interface ErrorDisplayProps {
  message: string;
  onDismiss?: () => void;
  onRetry?: () => void;
  showRetry?: boolean;
}

export function ErrorDisplay({
  message,
  onDismiss,
  onRetry,
  showRetry = true,
}: ErrorDisplayProps) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      role="alert"
      aria-live="assertive"
      className="w-full max-w-2xl mx-auto px-4"
    >
      <div className="p-8 rounded-3xl glass-panel border-rose-500/20 bg-rose-500/[0.02] shadow-[0_32px_64px_rgba(239,68,68,0.1)]">
        <div className="flex flex-col md:flex-row items-center md:items-start gap-6">
          <div className="w-16 h-16 rounded-2xl flex items-center justify-center bg-rose-500/10 border border-rose-500/20 shrink-0">
            <AlertCircle className="w-8 h-8 text-rose-400" aria-hidden="true" />
          </div>
          
          <div className="flex-1 text-center md:text-left space-y-4">
            <div>
              <h3 className="text-xl font-black text-white uppercase font-heading tracking-tight mb-2">
                Investigation Protocol Violated
              </h3>
              <div className="h-0.5 w-12 bg-rose-500/30 rounded-full mx-auto md:mx-0 mb-4" />
              <p className="text-sm font-medium text-rose-200/60 leading-relaxed break-words">
                {message}
              </p>
            </div>

            <div className="flex flex-col sm:flex-row gap-4 pt-2 justify-center md:justify-start">
              {showRetry && onRetry && (
                <button
                  onClick={onRetry}
                  className="btn-pill-primary px-8 py-3 text-[10px] gap-2 bg-rose-500 text-white hover:bg-rose-400 shadow-[0_0_24px_rgba(239,68,68,0.3)] border-none"
                >
                  <RotateCcw className="w-4 h-4" aria-hidden="true" />
                  Request Re-scan
                </button>
              )}
              {onDismiss && (
                <button
                  onClick={onDismiss}
                  className="btn-pill-secondary px-8 py-3 text-[10px] gap-2 border-white/5 active:scale-95"
                >
                  <X className="w-4 h-4" aria-hidden="true" />
                  Clear Alert
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
