"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { motion, useReducedMotion } from "framer-motion";
import { FileText, Music2, X } from "lucide-react";
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
  const prefersReducedMotion = useReducedMotion();
  const [mounted, setMounted] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);

  const closeModal = useCallback(() => {
    playSound("click");
    onDismiss();
  }, [playSound, onDismiss]);

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
      className="fixed inset-0 z-[9999] flex items-center justify-center p-4 fc-modal-backdrop"
      onMouseDown={(e) => { if (e.target === e.currentTarget) { playSound("click"); onDismiss(); } }}
    >
      <div className="relative w-full max-w-xl" onClick={(e) => e.stopPropagation()} ref={dialogRef}>
        <motion.div
          initial={prefersReducedMotion ? false : { opacity: 0, scale: 0.98, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={prefersReducedMotion ? {} : { opacity: 0, scale: 0.99, y: 5 }}
          transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
          className="fc-surface-overlay relative overflow-hidden"
        >
          <div className="p-8 sm:p-10 flex flex-col text-left">
            <button
              type="button"
              onClick={closeModal}
              aria-label="Close evidence dialog"
              data-testid="success-modal-close"
              className="absolute top-6 right-6 w-8 h-8 flex items-center justify-center fc-text-faint hover:fc-text-primary transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 rounded-full"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="space-y-6 w-full mb-8">
              <div>
                <p className="fc-eyebrow fc-text-faint mb-2" aria-hidden="true">
                  Status: Secured
                </p>
                <h2 id="success-modal-title" className="text-3xl font-heading font-bold text-white">
                  Evidence Ready
                </h2>
              </div>

              <div className="relative overflow-hidden border border-white/10 rounded-2xl bg-white/[0.01]" aria-label={`Preview of ${file.name}`}>
                <div className="aspect-video w-full flex items-center justify-center overflow-hidden relative">
                  {isAudio && previewUrl ? (
                    <div className="w-full px-6 py-8 flex flex-col items-center gap-4">
                      <Music2 className="w-10 h-10 fc-text-muted" aria-hidden="true" />
                      <audio
                        controls
                        src={previewUrl}
                        className="w-full rounded-none"
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
                    <div className="flex flex-col items-center gap-3 fc-text-muted" aria-hidden="true">
                      <FileText className="w-12 h-12" strokeWidth={1} />
                      <span className="fc-eyebrow fc-text-faint">Data Secured</span>
                    </div>
                  )}
                </div>
              </div>

              {/* File metadata */}
              <div className="flex items-center justify-between px-2 pt-2" aria-hidden="true">
                <div className="flex flex-col gap-1">
                  <p className="text-sm font-mono font-medium text-white truncate max-w-[300px]">{file.name}</p>
                  <span className="fc-eyebrow fc-text-muted">
                    {file.type || "binary/octet-stream"}
                  </span>
                </div>
                <div className="text-right">
                  <span className="text-sm font-mono font-bold text-white">
                    {(file.size / (1024 * 1024)).toFixed(2)} MB
                  </span>
                </div>
              </div>
            </div>

            <div className="flex w-full gap-4 mt-2">
              <button
                type="button"
                onClick={() => { playSound("click"); onNewUpload(); }}
                disabled={isStarting}
                className="fc-btn-secondary flex-1 disabled:opacity-50 disabled:cursor-not-allowed"
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
                className="fc-btn-primary flex-1 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isStarting ? (
                  <>
                    <div className="w-1.5 h-1.5 bg-white rounded-full animate-pulse" aria-hidden="true" />
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
