"use client";

import { useCallback, useEffect, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { FileText, X } from "lucide-react";
import { useSound } from "@/hooks/useSound";

export interface UploadSuccessModalProps {
  file: File;
  onNewUpload: () => void;
  onStartAnalysis: () => Promise<void> | void;
  onDismiss: () => void;
}

export function UploadSuccessModal({ file, onNewUpload, onStartAnalysis, onDismiss }: UploadSuccessModalProps) {
  const { playSound } = useSound();
  const prefersReducedMotion = useReducedMotion();
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);

  const closeModal = useCallback(() => {
    playSound("click");
    onDismiss();
  }, [playSound, onDismiss]);

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

  const isImage = file.type.startsWith("image/");
  const isVideo = file.type.startsWith("video/");
  const isAudio = file.type.startsWith("audio/");

  return (
    <motion.div
      initial={prefersReducedMotion ? false : { opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={prefersReducedMotion ? {} : { opacity: 0, y: 4 }}
      transition={{ duration: 0.16, ease: "easeOut" }}
      className="p-8 sm:p-10 flex flex-col text-left"
    >
      <button
        type="button"
        onClick={closeModal}
        aria-label="Close evidence dialog"
        data-testid="success-modal-close"
        className="absolute top-5 right-5 w-10 h-10 flex items-center justify-center fc-text-muted hover:fc-text-primary hover:bg-white/5 border border-transparent hover:border-white/10 fc-transition fc-focus-ring rounded-full cursor-pointer"
      >
        <X className="w-5 h-5" aria-hidden="true" />
      </button>

      <div className="space-y-6 w-full mb-8">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" aria-hidden="true" />
            <p className="fc-eyebrow fc-text-success uppercase tracking-widest text-[11px]" aria-hidden="true">
              Status: Secured
            </p>
          </div>
          <h2 className="text-xl lg:text-2xl font-heading font-bold fc-text-primary">
            Evidence Ready
          </h2>
        </div>

        <div role="region" aria-label={`Preview of ${file.name}`} className="relative overflow-hidden fc-surface-quiet">
          <div className="aspect-video w-full flex items-center justify-center overflow-hidden relative">
            {isAudio && previewUrl ? (
              <div className="w-full px-6 py-8 flex flex-col items-center gap-5">
                {/* Simulated Waveform Visualizer */}
                <div className="flex items-end justify-center gap-1.5 h-16 w-full max-w-[280px]" aria-hidden="true">
                  {[40, 60, 30, 80, 50, 70, 90, 45, 65, 85, 35, 55, 75, 40, 60, 30, 80, 50, 70, 90, 45].map((h, index) => (
                    <div
                      key={index}
                      className="w-[3px] bg-primary/45 rounded-full fc-transition"
                      style={{
                        height: `${h}%`,
                        animation: `fc-marker-blink ${1.2 + (index % 5) * 0.15}s ease-in-out infinite`,
                      }}
                    />
                  ))}
                </div>
                
                <audio
                  controls
                  src={previewUrl}
                  className="w-full max-w-[320px] opacity-80 invert grayscale accent-primary scale-95"
                  aria-label={`Audio preview of ${file.name}`}
                />
              </div>
            ) : isImage && previewUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={previewUrl}
                alt={`Evidence preview: ${file.name}`}
                className="absolute inset-0 w-full h-full object-contain"
              />
            ) : isVideo && previewUrl ? (
              <video
                src={previewUrl}
                className="w-full h-full object-contain"
                autoPlay={prefersReducedMotion === false}
                muted
                loop={prefersReducedMotion === false}
                playsInline
                controls
                aria-label={`Video preview of ${file.name}`}
              />
            ) : (
              <div className="flex flex-col items-center gap-4 relative z-10 py-6">
                <div className="w-14 h-14 rounded-2xl flex items-center justify-center bg-white/5 border border-white/10 mb-1 relative">
                  <FileText className="w-6 h-6 fc-text-secondary" strokeWidth={1.5} aria-hidden="true" />
                  <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-success rounded-full ring-2 ring-[#02040A] animate-pulse" />
                </div>
                <div className="text-center">
                  <span className="fc-eyebrow fc-text-secondary tracking-widest block mb-1">
                    CRYPTOGRAPHIC LOCK
                  </span>
                  <p className="text-xs fc-text-muted font-mono">
                    SHA-256 Hash Prepared
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between px-2 pt-2">
          <div className="flex flex-col gap-1">
            <p
              className="text-sm font-medium fc-text-primary truncate max-w-[300px]"
              title={file.name}
            >
              {file.name}
            </p>
            <span className="text-xs font-mono fc-text-muted">
              {file.type || "binary/octet-stream"}
            </span>
          </div>
          <div className="text-right">
            <span className="text-sm font-bold fc-text-primary">
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
          className="fc-btn-secondary flex-1"
        >
          Reselect File
        </button>
        <button
          type="button"
          data-testid="upload-start-analysis"
          autoFocus
          onClick={async () => {
            setIsStarting(true);
            try {
              await onStartAnalysis();
            } finally {
              setIsStarting(false);
            }
          }}
          disabled={isStarting}
          aria-busy={isStarting}
          className="fc-btn-primary flex-1"
        >
          {isStarting ? (
            <>
              <span className="w-3.5 h-3.5 rounded-full border-2 border-white/30 border-t-white animate-spin flex-shrink-0" aria-hidden="true" />
              Opening Analysis
            </>
          ) : (
            "Begin Analysis"
          )}
        </button>
      </div>
    </motion.div>
  );
}
