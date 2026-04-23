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
      <div className="p-8 rounded-3xl bg-danger/[0.04] backdrop-blur-xl border border-danger/20 shadow-[0_32px_64px_rgba(239,68,68,0.1)]">
        <div className="flex flex-col md:flex-row items-center md:items-start gap-6">
          <div className="w-16 h-16 rounded-2xl flex items-center justify-center bg-rose-500/10 border border-rose-500/20 shrink-0">
            <AlertCircle className="w-8 h-8 text-rose-400" aria-hidden="true" />
          </div>
          
          <div className="flex-1 text-center md:text-left space-y-4">
            <div>
              <h3 className="text-xl font-bold text-white tracking-tight mb-2">
                Investigation Protocol Error
              </h3>
              <div className="h-0.5 w-12 bg-rose-500/20 rounded-full mx-auto md:mx-0 mb-4" />
              <p className="text-sm font-medium text-white/70 leading-relaxed break-words">
                {message}
              </p>
            </div>

            <div className="flex flex-col sm:flex-row gap-4 pt-2 justify-center md:justify-start">
              {showRetry && onRetry && (
                <button
                  onClick={onRetry}
                  className="inline-flex items-center rounded-full border border-white/15 text-white/70 hover:border-white/30 hover:text-white px-6 py-2.5 text-sm font-semibold gap-2 transition-all"
                >
                  <RotateCcw className="w-4 h-4" aria-hidden="true" />
                  Request Re-scan
                </button>
              )}
              {onDismiss && (
                <button
                  onClick={onDismiss}
                  className="inline-flex items-center rounded-full border border-white/15 text-white/70 hover:border-white/30 hover:text-white px-6 py-2.5 text-sm font-semibold gap-2 transition-all active:scale-95"
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
