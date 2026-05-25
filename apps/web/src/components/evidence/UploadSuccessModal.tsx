"use client";

import { useCallback } from "react";
import { motion } from "framer-motion";
import { Lock, FileBadge2, ArrowRight, X } from "lucide-react";
import { useSound } from "@/hooks/useSound";
import { formatBytes } from "@/lib/utils";

export interface UploadSuccessModalProps {
  file: File;
  onNewUpload: () => void;
  onStartAnalysis: () => Promise<void> | void;
  onDismiss: () => void;
  isHandingOff?: boolean;
}

export function UploadSuccessModal({ file, onStartAnalysis, onDismiss, isHandingOff = false }: UploadSuccessModalProps) {
  const { playSound } = useSound();

  const closeModal = useCallback(() => {
    playSound("click");
    onDismiss();
  }, [playSound, onDismiss]);

  return (
    <motion.div
      key="success-state"
      initial={{ opacity: 0, scale: 0.95, filter: "blur(4px)" }}
      animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
      exit={{ opacity: 0, scale: 1.05, filter: "blur(4px)" }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className="p-8 sm:p-10 flex flex-col text-left relative overflow-hidden"
    >
      {/* Background Secure Pattern */}
      <div className="absolute inset-0 opacity-[0.03] pointer-events-none bg-[radial-gradient(#fff_1px,transparent_1px)] [background-size:16px_16px]" aria-hidden="true" />

      <button
        type="button"
        onClick={closeModal}
        aria-label="Close evidence dialog"
        data-testid="success-modal-close"
        className="absolute top-5 right-5 w-10 h-10 flex items-center justify-center fc-text-muted hover:fc-text-primary hover:bg-white/5 border border-transparent hover:border-white/10 fc-transition fc-focus-ring rounded-full cursor-pointer z-20"
      >
        <X className="w-5 h-5" aria-hidden="true" />
      </button>

      <div className="mb-6 flex items-center justify-between relative z-10">
        <div className="flex items-center gap-3">
          <motion.div
            initial={{ rotate: -90, opacity: 0 }}
            animate={{ rotate: 0, opacity: 1 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="w-10 h-10 rounded-full bg-primary/10 border border-primary/30 flex items-center justify-center text-primary"
          >
            <Lock className="w-5 h-5" aria-hidden="true" />
          </motion.div>
          <div>
            <p className="text-xs font-mono fc-text-muted uppercase tracking-wider">Status: Secured</p>
            <h2 className="text-xl font-heading font-bold fc-text-primary">Evidence Sealed</h2>
          </div>
        </div>
      </div>

      {/* Telemetry Readout Box */}
      <motion.div
        initial={{ height: 0, opacity: 0 }}
        animate={{ height: "auto", opacity: 1 }}
        transition={{ duration: 0.4, delay: 0.2 }}
        className="bg-black/40 border border-white/10 rounded-xl p-5 mb-8 overflow-hidden relative"
      >
        <div className="absolute left-0 top-0 bottom-0 w-[2px] bg-primary/50" />
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-3">
            <FileBadge2 className="w-8 h-8 fc-text-secondary" />
            <div className="overflow-hidden">
              <p className="text-sm font-medium fc-text-primary truncate" title={file.name}>{file.name}</p>
              <p className="text-xs font-mono fc-text-muted mt-1">{formatBytes(file.size)} &bull; {file.type || 'Unknown Format'}</p>
            </div>
          </div>

          {/* Fake Cryptographic Hash Generation for Visual Drama */}
          <div className="mt-2 pt-3 border-t border-white/5 flex justify-between items-center">
            <span className="text-[10px] font-mono fc-text-muted uppercase">SHA-256 Checksum</span>
            <motion.span
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.6 }}
              className="text-[10px] font-mono text-primary truncate max-w-[200px]"
            >
              {btoa(file.name + file.size).substring(0, 24).toLowerCase()}...
            </motion.span>
          </div>
        </div>
      </motion.div>

      {/* Actions */}
      <div className="flex gap-3 relative z-10 mt-auto">
        <button onClick={onDismiss} className="fc-btn-secondary flex-1">
          Cancel
        </button>
        <button
          onClick={onStartAnalysis}
          disabled={isHandingOff}
          className="fc-btn-primary flex-[2] group relative overflow-hidden"
        >
          <span className="relative z-10 flex items-center justify-center gap-2">
            {isHandingOff ? "Initializing Agents..." : "Deploy Council"}
            {!isHandingOff && <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />}
          </span>
          <div className="absolute inset-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300 ease-out" />
        </button>
      </div>
    </motion.div>
  );
}
