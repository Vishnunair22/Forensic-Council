"use client";

import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { 
  AlertTriangle, 
  Home as HomeIcon, 
  RefreshCcw, 
  Terminal,
  ShieldAlert
} from "lucide-react";
import { useSound } from "@/hooks/useSound";

interface ForensicErrorModalProps {
  isVisible: boolean;
  title?: string;
  message?: string;
  errorCode?: string;
  onRetry?: () => void;
  onHome?: () => void;
}

export function ForensicErrorModal({
  isVisible,
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

  return createPortal(
    <AnimatePresence>
      {isVisible && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          role="dialog"
          aria-modal="true"
          aria-labelledby="forensic-error-title"
          aria-describedby="forensic-error-desc"
          className="fixed inset-0 z-[20000] flex items-center justify-center p-6 bg-slate-950/90 backdrop-blur-3xl"
        >
          <div className="relative w-full max-w-2xl">
            <motion.div
              initial={{ opacity: 0, scale: 0.98, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.98, y: 20 }}
              transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
              className="horizon-card p-1 border-danger/20"
            >
              <div className="bg-[#020617] rounded-[inherit] p-10">
                
                {/* --- Header Identity --- */}
                <div className="flex items-center gap-3 mb-10">
                  <ShieldAlert className="w-4 h-4 text-danger" />
                  <span className="text-[10px] font-mono font-bold tracking-[0.3em] text-danger/60 uppercase">
                    Quarantine_Protocol_Active
                  </span>
                </div>

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
                    <div>
                      <h2 id="forensic-error-title" className="text-4xl font-heading font-bold text-white tracking-tight mb-4">
                        {title}
                      </h2>
                      <p id="forensic-error-desc" className="text-base font-medium text-white/40 leading-relaxed">
                        {message}
                      </p>
                    </div>

                    {/* Diagnostic Trace HUD */}
                    <div className="bg-white/[0.02] border border-white/5 rounded-xl p-6 space-y-3">
                      <div className="flex items-center gap-2 text-[10px] font-mono font-bold text-white/20 mb-2">
                        <Terminal className="w-3 h-3" />
                        <span>DIAGNOSTIC_TRACE</span>
                      </div>
                      <div className="flex justify-between items-center text-[11px] font-mono">
                        <span className="text-white/30">ERROR_ID</span>
                        <span className="text-danger font-bold">{errorCode}</span>
                      </div>
                      <div className="flex justify-between items-center text-[11px] font-mono">
                        <span className="text-white/30">UTC_TIME</span>
                        <span className="text-white/60">{new Date().toISOString().split('T')[1].slice(0, 8)}</span>
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex gap-4">
                      {onRetry && (
                        <button 
                          onClick={onRetry}
                          className="flex-1 btn-horizon-primary py-4 text-xs border-danger/40 bg-danger/10 text-danger hover:bg-danger/20 flex items-center justify-center gap-3"
                        >
                          <RefreshCcw className="w-4 h-4" />
                          Retry Analysis
                        </button>
                      )}
                      {onHome && (
                        <button 
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

                {/* Footer Metadata */}
                <div className="mt-12 pt-8 border-t border-white/5 flex items-center justify-between text-[9px] font-mono text-white/20 uppercase tracking-widest">
                  <div className="flex items-center gap-2">
                    <span className="w-1 h-1 rounded-full bg-danger animate-pulse" />
                    <span>Pipeline_Halted</span>
                  </div>
                  <span>Secured_Session // VOID</span>
                </div>

              </div>
            </motion.div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}
