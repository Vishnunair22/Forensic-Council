"use client";

import React, { useEffect, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { motion, AnimatePresence } from "framer-motion";
import {
  Home as HomeIcon,
  RefreshCcw,
  Terminal,
  ShieldAlert,
  X
} from "lucide-react";
import { useSound } from "@/hooks/useSound";

interface ForensicErrorModalProps {
  isVisible: boolean;
  isTransient?: boolean;
  title?: string;
  message?: string;
  errorCode?: string;
  onRetry?: () => void;
  onHome?: () => void;
}

export function ForensicErrorModal({
  isVisible,
  isTransient = false,
  title = "Analysis Disrupted",
  message = "The forensic pipeline encountered a critical synchronization failure.",
  errorCode = "0xFC_PROTOCOL_ERR",
  onRetry,
  onHome
}: ForensicErrorModalProps) {
  const [mounted, setMounted] = useState(false);
  // F-L-4: pin the displayed UTC time at mount instead of recomputing every
  // render. Prevents drift on re-renders while the modal is open.
  const [utcStamp, setUtcStamp] = useState<string>("");
  const { playSound } = useSound();

  useEffect(() => {
    setMounted(true);
    setUtcStamp(new Date().toISOString().split("T")[1].slice(0, 8));
  }, []);

  useEffect(() => {
    if (isVisible && mounted) {
      // Refresh stamp each time the modal becomes visible so a re-opened
      // error reflects when *this* error happened, not the prior one.
      setUtcStamp(new Date().toISOString().split("T")[1].slice(0, 8));
      playSound("alert-error");
    }
  }, [isVisible, mounted, playSound]);

  if (!mounted) return null;

  return (
    <AnimatePresence>
      {isVisible && (
        <Dialog.Root open={isVisible} onOpenChange={(open) => { if (!open) (onHome ?? onRetry)?.(); }}>
          <Dialog.Portal forceMount>
            <Dialog.Overlay asChild>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="fixed inset-0 z-[20000] flex items-center justify-center p-6 fc-modal-backdrop"
              />
            </Dialog.Overlay>
            <Dialog.Content asChild>
              <motion.div
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 4 }}
                transition={{ duration: 0.16, ease: "easeOut" }}
                className="relative w-full max-w-xl focus:outline-none overflow-hidden fc-surface-overlay border-[var(--color-danger)]/30 rounded-3xl"
              >
                {/* Top accent */}
                <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[var(--color-danger)]/50 to-transparent" />

                <div className="p-8 sm:p-10 flex flex-col text-left">
                  {/* --- Header Identity --- */}
                  <div className="flex items-center gap-3 mb-8">
                    <div className="w-8 h-8 flex items-center justify-center border border-[var(--color-danger)]/30 rounded bg-[var(--color-danger)]/5">
                      <ShieldAlert className="w-4 h-4 text-[var(--color-danger)]" />
                    </div>
                    <span className="fc-eyebrow text-[var(--color-danger)]/60">
                      {isTransient ? "Stream Synchronization Lost" : "Quarantine Protocol Active"}
                    </span>
                  </div>

                  <Dialog.Title asChild>
                    <h2 className="text-3xl font-heading font-bold text-white mb-4">
                      {title}
                    </h2>
                  </Dialog.Title>

                  <Dialog.Description asChild>
                    <p className="text-sm font-medium fc-text-faint leading-relaxed mb-8">
                      {message}
                    </p>
                  </Dialog.Description>

                  <div className="flex flex-col gap-8">
                    {/* Diagnostic Trace HUD */}
                    <div className="border-t border-b border-[var(--color-danger)]/10 py-4 space-y-3">
                      <div className="flex items-center gap-2 fc-eyebrow text-[var(--color-danger)]/40 mb-2">
                        <Terminal className="w-3 h-3" />
                        <span>Diagnostic Trace</span>
                      </div>
                      <div className="flex justify-between items-center text-xs font-mono">
                        <span className="fc-text-faint">Error ID</span>
                        <span className="text-[var(--color-danger)] font-bold">{errorCode}</span>
                      </div>
                      <div className="flex justify-between items-center text-xs font-mono">
                        <span className="fc-text-faint">UTC Time</span>
                        <span className="text-white/60">{utcStamp}</span>
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex gap-4">
                      {onRetry && (
                        <button
                          type="button"
                          onClick={onRetry}
                          className="flex-1 fc-btn-danger gap-2"
                        >
                          <RefreshCcw className="w-4 h-4" />
                          Retry Analysis
                        </button>
                      )}
                      {onHome && (
                        <button
                          type="button"
                          onClick={onHome}
                          className="flex-1 fc-btn-secondary gap-2"
                        >
                          <HomeIcon className="w-4 h-4" />
                          Return to Hub
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Close button for accessibility */}
                  <Dialog.Close asChild>
                    <button
                      className="absolute top-6 right-6 w-8 h-8 flex items-center justify-center fc-text-muted hover:text-white/90 transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-danger)]/50 rounded"
                      aria-label="Close"
                    >
                      <X className="w-5 h-5" />
                    </button>
                  </Dialog.Close>

                  {/* Footer Metadata */}
                  <div className="mt-8 pt-6 border-t border-white/5 flex items-center justify-between text-xs font-mono fc-text-faint tracking-widest">
                    <div className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-danger)] animate-pulse" />
                      <span>Pipeline Halted</span>
                    </div>
                    <span>Secured Session // Void</span>
                  </div>

                </div>
              </motion.div>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      )}
    </AnimatePresence>
  );
}
