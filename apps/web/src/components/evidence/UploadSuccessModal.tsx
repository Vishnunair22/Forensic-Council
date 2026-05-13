"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { motion } from "framer-motion";
import { CheckCircle2, FileText, X, Loader2 } from "lucide-react";
import { useSound } from "@/hooks/useSound";
import { useFocusTrap } from "@/hooks/useFocusTrap";

export interface UploadSuccessModalProps {
  file: File;
  onNewUpload: () => void;
  onStartAnalysis: () => Promise<void> | void;
  onDismiss: () => void;
}

export function UploadSuccessModal({ file, onNewUpload, onStartAnalysis, onDismiss }: UploadSuccessModalProps) {
  const { playSound } = useSound();
  const [mounted, setMounted] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);

  const closeModal = () => {
    playSound("click");
    onDismiss();
  };

  useFocusTrap(dialogRef, mounted, closeModal);

  useEffect(() => {
    setMounted(true);
    playSound("card_reveal");
  }, [playSound]);

  useEffect(() => {
    if (
      file.type.startsWith("image/") ||
      file.type.startsWith("video/") ||
      file.type.startsWith("audio/")
    ) {
      const url = URL.createObjectURL(file);
      setPreviewUrl(url);
      return () => URL.revokeObjectURL(url);
    }
  }, [file]);

  if (!mounted) return null;

  const isImage = file.type.startsWith("image/");
  const isVideo = file.type.startsWith("video/");
  const isAudio = file.type.startsWith("audio/");

  return createPortal(
    <motion.div
      role="dialog"
      aria-modal="true"
      aria-labelledby="success-modal-title"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: 0.12, ease: "easeIn" } }}
      transition={{ duration: 0.14, ease: "easeOut" }}
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-[#010208]/96 backdrop-blur-2xl p-4"
      onMouseDown={(e) => { if (e.target === e.currentTarget) { playSound("click"); onDismiss(); } }}
    >
      <div className="relative w-full max-w-xl" onClick={(e) => e.stopPropagation()} ref={dialogRef}>
        <motion.div
          initial={{ opacity: 0, scale: 0.97, y: 14 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.985, y: 6 }}
          transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
          className="horizon-card p-1 relative overflow-hidden"
        >
          <div
            className="rounded-[inherit] p-10 flex flex-col items-center text-center"
            style={{ background: "radial-gradient(ellipse 70% 40% at 50% 0%, rgba(52,211,153,0.05) 0%, #020617 55%)" }}
          >
            <button
              type="button"
              onClick={closeModal}
              aria-label="Close evidence dialog"
              data-testid="success-modal-close"
              className="absolute top-6 right-6 text-white/25 hover:text-white/70 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 rounded"
            >
              <X className="w-5 h-5" />
            </button>

            {/* Status icon */}
            <motion.div
              initial={{ scale: 0.5, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ type: "spring", bounce: 0.5, delay: 0.2 }}
              className="w-16 h-16 rounded-full bg-success/10 border border-success/20 text-success flex items-center justify-center mb-6 shadow-[0_0_20px_rgba(52,211,153,0.15)]"
              aria-hidden="true"
            >
              <CheckCircle2 className="w-8 h-8" />
            </motion.div>

            <div className="space-y-6 w-full mb-8">
              <div>
                <p className="text-[10px] font-mono font-bold tracking-[0.25em] text-[var(--color-success)]/60 uppercase mb-1.5" aria-hidden="true">
                  Evidence Secured
                </p>
                <h2 id="success-modal-title" className="text-2xl font-heading font-bold text-white">Evidence Ready</h2>
              </div>

              {/* Preview with HUD frame */}
              <div className="relative rounded-xl overflow-hidden border border-white/[0.07] bg-white/[0.02]" aria-label={`Preview of ${file.name}`}>
                <div className="aspect-video w-full flex items-center justify-center overflow-hidden relative">
                  {/* HUD corners */}
                  <div className="absolute top-3 left-3 w-4 h-4 border-t-2 border-l-2 border-primary/30 z-20 rounded-tl" aria-hidden="true" />
                  <div className="absolute top-3 right-3 w-4 h-4 border-t-2 border-r-2 border-primary/30 z-20 rounded-tr" aria-hidden="true" />
                  <div className="absolute bottom-3 left-3 w-4 h-4 border-b-2 border-l-2 border-primary/30 z-20 rounded-bl" aria-hidden="true" />
                  <div className="absolute bottom-3 right-3 w-4 h-4 border-b-2 border-r-2 border-primary/30 z-20 rounded-br" aria-hidden="true" />

                  {isAudio && previewUrl ? (
                    <div className="w-full px-6 py-8 flex flex-col items-center gap-4">
                      <FileText className="w-10 h-10 text-white/20" aria-hidden="true" />
                      <audio
                        controls
                        src={previewUrl}
                        className="w-full rounded-xl"
                        aria-label={`Audio preview of ${file.name}`}
                      />
                    </div>
                  ) : isImage && previewUrl ? (
                    /* eslint-disable-next-line @next/next/no-img-element */
                    <img
                      src={previewUrl}
                      alt={file.name}
                      className="absolute inset-0 w-full h-full object-cover"
                    />
                  ) : isVideo && previewUrl ? (
                    <video
                      src={previewUrl}
                      className="w-full h-full object-cover"
                      autoPlay
                      muted
                      loop
                      playsInline
                      aria-label={file.name}
                    />
                  ) : (
                    <div className="flex flex-col items-center gap-3 text-white/20" aria-hidden="true">
                      <FileText className="w-12 h-12" strokeWidth={1} />
                      <span className="text-[10px] font-mono tracking-widest uppercase">DATA_SECURED</span>
                    </div>
                  )}

                  {/* File metadata HUD */}
                  <div className="absolute inset-x-0 bottom-0 p-5 bg-gradient-to-t from-black/70 via-black/40 to-transparent backdrop-blur-[2px] border-t border-white/5 flex items-center justify-between" aria-hidden="true">
                    <div className="text-left">
                      <p className="text-xs font-mono text-white/80 truncate max-w-[200px]">{file.name}</p>
                      <span className="text-[9px] font-mono text-white/30 uppercase tracking-tighter">
                        {file.type || "binary/octet-stream"}
                      </span>
                    </div>
                    <div className="text-right">
                      <span className="text-[10px] font-mono font-bold text-primary border border-primary/20 px-2 py-0.5 rounded bg-primary/5">
                        {(file.size / (1024 * 1024)).toFixed(2)} MB
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex w-full gap-4">
              <button
                type="button"
                onClick={() => { playSound("click"); onNewUpload(); }}
                disabled={isStarting}
                className="btn-horizon-outline flex-1 py-4 text-xs disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Reselect File
              </button>
              <button
                type="button"
                data-testid="upload-start-analysis"
                onClick={async () => {
                  setIsStarting(true);
                  try {
                    await onStartAnalysis();
                  } finally {
                    setIsStarting(false);
                  }
                }}
                disabled={isStarting}
                className="btn-horizon-primary flex-1 py-4 text-xs flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isStarting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                    Opening Analysis
                  </>
                ) : (
                  "Begin Analysis"
                )}
              </button>
            </div>
          </div>
        </motion.div>
      </div>
    </motion.div>,
    document.body
  );
}
