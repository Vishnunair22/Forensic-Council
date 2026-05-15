"use client";

import React, { useEffect, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertTriangle,
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
  const { playSound } = useSound();

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (isVisible && mounted) {
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
                className="fixed inset-0 z-[20000] flex items-center justify-center p-6"
                style={{ background: "rgba(1,2,8,0.92)", backdropFilter: "blur(28px)", WebkitBackdropFilter: "blur(28px)" }}
              />
            </Dialog.Overlay>
            <Dialog.Content asChild>
              <motion.div
                initial={{ opacity: 0, scale: 0.97, y: 18 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.97, y: 10 }}
                transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                className="relative w-full max-w-xl focus:outline-none overflow-hidden rounded-2xl"
                style={{
                  background: "rgba(6,10,20,0.98)",
                  border: "1px solid rgba(239,68,105,0.18)",
                  boxShadow: "0 32px 80px rgba(0,0,0,0.75), 0 0 0 1px rgba(239,68,105,0.06), inset 0 1px 0 rgba(255,255,255,0.04)",
                }}
              >
                {/* Top accent */}
                <div
                  className="absolute inset-x-0 top-0 h-px"
                  style={{ background: "linear-gradient(90deg, transparent, rgba(239,68,105,0.5) 50%, transparent)" }}
                />

                <div className="p-8 sm:p-10">

                  {/* --- Header Identity --- */}
                  <div className="flex items-center gap-3 mb-10">
                    <ShieldAlert className="w-4 h-4 text-danger" />
                    <span className="text-[10px] font-mono font-bold tracking-[0.3em] text-danger/60">
                      {isTransient ? "Stream Synchronization Lost" : "Quarantine Protocol Active"}
                    </span>
                  </div>

                  <Dialog.Title asChild>
                    <h2 className="text-4xl font-heading font-bold text-white tracking-tight mb-4">
                      {title}
                    </h2>
                  </Dialog.Title>

                  <Dialog.Description asChild>
                    <p className="text-base font-medium text-white/40 leading-relaxed mb-8">
                      {message}
                    </p>
                  </Dialog.Description>

                  <div className="flex flex-col md:flex-row gap-12 items-start">
                    {/* Aperture Node (Red) */}
                    <div className="relative w-24 h-24 shrink-0 flex items-center justify-center">
                      <motion.div
                        animate={{ rotate: 360 }}
                        transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
                        className="absolute inset-0 rounded-full border border-danger/20 border-dashed"
                      />
                      <AlertTriangle className="w-10 h-10 text-danger relative z-10" />
                    </div>

                    <div className="flex-1 space-y-8">
                      {/* Diagnostic Trace HUD */}
                      <div className="bg-white/[0.02] border border-white/5 rounded-xl p-6 space-y-3">
                        <div className="flex items-center gap-2 text-[10px] font-mono font-bold text-white/20 mb-2">
                          <Terminal className="w-3 h-3" />
                          <span>Diagnostic Trace</span>
                        </div>
                        <div className="flex justify-between items-center text-[11px] font-mono">
                          <span className="text-white/30">Error ID</span>
                          <span className="text-danger font-bold">{errorCode}</span>
                        </div>
                        <div className="flex justify-between items-center text-[11px] font-mono">
                          <span className="text-white/30">UTC Time</span>
                          <span className="text-white/60">{new Date().toISOString().split('T')[1].slice(0, 8)}</span>
                        </div>
                      </div>

                      {/* Actions */}
                      <div className="flex gap-4">
                        {onRetry && (
                          <button
                            type="button"
                            onClick={onRetry}
                            className="flex-1 btn-horizon-primary py-4 text-xs border-danger/40 bg-danger/10 text-danger hover:bg-danger/20 flex items-center justify-center gap-3"
                          >
                            <RefreshCcw className="w-4 h-4" />
                            Retry Analysis
                          </button>
                        )}
                        {onHome && (
                          <button
                            type="button"
                            onClick={onHome}
                            className="flex-1 btn-horizon-outline py-4 text-xs flex items-center justify-center gap-3"
                          >
                            <HomeIcon className="w-4 h-4" />
                            Return to Hub
                          </button>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Close button for accessibility */}
                  <Dialog.Close asChild>
                    <button
                      className="absolute top-4 right-4 inline-flex items-center justify-center w-6 h-6 rounded-full text-white/40 hover:text-white hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-danger"
                      aria-label="Close"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </Dialog.Close>

                  {/* Footer Metadata */}
                  <div className="mt-12 pt-8 border-t border-white/5 flex items-center justify-between text-[9px] font-mono text-white/20 tracking-widest">
                    <div className="flex items-center gap-2">
                      <span className="w-1 h-1 rounded-full bg-danger animate-pulse" />
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
