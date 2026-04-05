"use client";

"use client";

/**
 * ErrorDisplay Component
 * ======================
 *
 * Displays error messages during investigation.
 * Shows error details and recovery options.
 */

import { AlertCircle, RotateCcw, X } from "lucide-react";

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
    <div
      role="alert"
      aria-live="assertive"
      className="w-full max-w-2xl mx-auto"
    >
      <div className="p-6 rounded-2xl bg-red-500/[0.06] border border-red-500/25 backdrop-blur-xl shadow-[0_0_40px_rgba(239,68,68,0.06),inset_0_1px_0_rgba(255,255,255,0.04)]">
        {/* Header */}
        <div className="flex items-start gap-4">
          <div className="mt-1">
            <AlertCircle
              className="w-6 h-6 text-red-400 flex-shrink-0"
              aria-hidden="true"
            />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-lg font-semibold text-red-300 mb-2">
              Investigation Error
            </h3>
            <p className="text-sm text-red-200 mb-4 break-words">{message}</p>

            {/* Action Buttons */}
            <div className="flex gap-3 flex-wrap">
              {showRetry && onRetry && (
                <button
                  onClick={onRetry}
                  className="btn-pill-primary px-5 py-2"
                >
                  <RotateCcw className="w-4 h-4" aria-hidden="true" />
                  Try Again
                </button>
              )}
              {onDismiss && (
                <button
                  onClick={onDismiss}
                  className="btn-pill-secondary px-5 py-2"
                >
                  <X className="w-4 h-4" aria-hidden="true" />
                  Dismiss
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
