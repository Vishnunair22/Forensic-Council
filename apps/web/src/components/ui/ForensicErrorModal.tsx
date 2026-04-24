"use client";

import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { 
  AlertTriangle, 
  Home as HomeIcon, 
  RefreshCcw, 
  ChevronRight, 
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
      playSound("alert-error"); // Needs to be added to useSound or mapped
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
          className="fixed inset-0 z-[20000] flex items-center justify-center p-6"
        >
          {/* Backdrop Blur */}
          <div className="absolute inset-0 bg-black/90 backdrop-blur-[60px]" />

          {/* Ambient Danger Glow */}
          <motion.div 
            className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[80vw] h-[80vw] rounded-full opacity-30 blur-[150px] pointer-events-none"
            style={{ background: "radial-gradient(circle, rgba(239, 68, 68, 0.1) 0%, transparent 70%)" }}
            animate={{ opacity: [0.2, 0.4, 0.2], scale: [0.9, 1.1, 0.9] }}
            transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
          />

          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 30 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 15 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            className="relative w-full max-w-2xl bg-white/[0.03] border border-red-500/20 rounded-[2.5rem] p-10 shadow-[0_0_100px_rgba(239,68,68,0.15)] overflow-hidden"
          >
            {/* Header Identity */}
            <div className="flex items-center gap-3 mb-10">
              <div className="p-2 rounded-lg bg-red-500/10 border border-red-500/20">
                <ShieldAlert className="w-4 h-4 text-red-500" />
              </div>
              <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-red-500/60 uppercase">
                Quarantine Protocol Active
              </span>
            </div>

            <div className="flex flex-col md:flex-row gap-10 items-start">
              {/* Left Side: Icon */}
              <div className="flex-shrink-0 w-24 h-24 rounded-3xl bg-red-500/5 border border-red-500/10 flex items-center justify-center relative group">
                <motion.div 
                  className="absolute inset-0 bg-red-500/10 rounded-3xl blur-xl"
                  animate={{ opacity: [0, 1, 0] }}
                  transition={{ duration: 2, repeat: Infinity }}
                />
                <AlertTriangle className="w-12 h-12 text-red-500 relative z-10" strokeWidth={1.5} />
              </div>

              {/* Right Side: Content */}
              <div className="flex-1 space-y-6">
                <div>
                  <h2 className="text-4xl font-black text-white tracking-tighter mb-4 leading-none">
                    {title}
                  </h2>
                  <p className="text-lg font-medium text-white/50 tracking-wide leading-relaxed">
                    {message}
                  </p>
                </div>

                {/* Diagnostic Trace */}
                <div className="bg-black/40 border border-white/5 rounded-2xl p-6 font-mono text-[11px] space-y-3">
                  <div className="flex items-center gap-2 text-white/20">
                    <Terminal className="w-3 h-3" />
                    <span>SYSTEM DIAGNOSTIC</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-white/40">ERROR_IDENTIFIER</span>
                    <span className="text-red-500/80 font-bold">{errorCode}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-white/40">TIME_STAMP</span>
                    <span className="text-white/60">{new Date().toISOString()}</span>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex flex-wrap gap-4 pt-4">
                  {onRetry && (
                    <button 
                      onClick={onRetry}
                      className="group flex items-center gap-3 px-8 py-4 bg-white text-black font-bold rounded-full hover:bg-primary hover:text-white transition-all active:scale-95"
                    >
                      <RefreshCcw className="w-4 h-4 group-hover:rotate-180 transition-transform duration-500" />
                      Retry Analysis
                    </button>
                  )}
                  {onHome && (
                    <button 
                      onClick={onHome}
                      className="group flex items-center gap-3 px-8 py-4 bg-white/[0.05] border border-white/10 text-white font-bold rounded-full hover:bg-white/[0.1] transition-all active:scale-95"
                    >
                      <HomeIcon className="w-4 h-4 text-white/40" />
                      Return to Hub
                    </button>
                  )}
                </div>
              </div>
            </div>

            {/* Subtle Footer */}
            <div className="mt-12 pt-8 border-t border-white/5 flex items-center justify-between text-[10px] font-mono text-white/20">
              <div className="flex items-center gap-2">
                <ChevronRight className="w-3 h-3" />
                <span>CLEANUP TASKS INITIATED</span>
              </div>
              <span>SECURED_SESSION // {errorCode.split('_')[1] || 'VOID'}</span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}
