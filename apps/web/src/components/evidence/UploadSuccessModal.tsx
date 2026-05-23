"use client";

import { useCallback, useEffect, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { FileText, Music2, X } from "lucide-react";
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
        className="absolute top-5 right-5 w-10 h-10 flex items-center justify-center fc-text-muted hover:fc-text-primary fc-transition fc-focus-ring rounded-full cursor-pointer"
      >
        <X className="w-5 h-5" aria-hidden="true" />
      </button>

      <div className="space-y-6 w-full mb-8">
        <div>
          <p className="fc-eyebrow fc-text-muted mb-2" aria-hidden="true">
            Status: Secured
          </p>
          <h2 className="text-2xl font-heading font-bold fc-text-primary">
            Evidence Ready
          </h2>
        </div>

        <div role="region" aria-label={`Preview of ${file.name}`} className="relative overflow-hidden border border-white/10 rounded-2xl bg-white/[0.03]">
          <div className="aspect-video w-full flex items-center justify-center overflow-hidden relative">
            {isAudio && previewUrl ? (
              <div className="w-full px-6 py-8 flex flex-col items-center gap-4">
                <Music2 className="w-8 h-8 fc-text-muted" aria-hidden="true" />
                <audio
                  controls
                  src={previewUrl}
                  className="w-full opacity-80 invert grayscale"
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
              <div className="flex flex-col items-center gap-3 fc-text-muted">
                <FileText className="w-8 h-8" strokeWidth={1.5} aria-hidden="true" />
                <span className="fc-eyebrow fc-text-muted">Data Secured</span>
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
