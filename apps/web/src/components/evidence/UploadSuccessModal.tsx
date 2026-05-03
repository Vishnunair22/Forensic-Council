"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { motion } from "framer-motion";
import Image from "next/image";
import { CheckCircle2, FileText, X, Loader2 } from "lucide-react";

export interface UploadSuccessModalProps {
  file: File;
  onNewUpload: () => void;
  onStartAnalysis: () => Promise<void> | void;
}

export function UploadSuccessModal({ file, onNewUpload, onStartAnalysis }: UploadSuccessModalProps) {
  const [mounted, setMounted] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);

  useEffect(() => {
    setMounted(true);
    const originalBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = originalBodyOverflow || "unset";
    };
  }, []);

  useEffect(() => {
    if (file.type.startsWith("image/") || file.type.startsWith("video/")) {
      const url = URL.createObjectURL(file);
      setPreviewUrl(url);
      return () => URL.revokeObjectURL(url);
    }
  }, [file]);

  useEffect(() => {
    const onEsc = (e: KeyboardEvent) => { if (e.key === "Escape") onNewUpload(); };
    window.addEventListener("keydown", onEsc);
    return () => window.removeEventListener("keydown", onEsc);
  }, [onNewUpload]);

  if (!mounted) return null;

  const isImage = file.type.startsWith("image/");
  const isVideo = file.type.startsWith("video/");

  return createPortal(
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.18, ease: "easeOut" }}
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-slate-950/80 backdrop-blur-xl p-4"
    >
      <div className="relative w-full max-w-xl" onClick={(e) => e.stopPropagation()}>
        <motion.div
          initial={{ opacity: 0, scale: 0.985, y: 8 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.985, y: 8 }}
          transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
          className="horizon-card p-1 relative overflow-hidden"
        >
          <div className="bg-[#020617] rounded-[inherit] p-10 flex flex-col items-center text-center">
            <button
              onClick={() => { onNewUpload(); }}
              aria-label="Close"
              data-testid="success-modal-close"
              className="absolute top-6 right-6 text-white/40 hover:text-primary"
            >
              <X className="w-5 h-5" />
            </button>

            {/* Status Icon */}
            <motion.div
              initial={{ scale: 0.5, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ type: "spring", bounce: 0.5, delay: 0.2 }}
              className="w-16 h-16 rounded-full bg-success/10 border border-success/20 text-success flex items-center justify-center mb-6 shadow-[0_0_30px_rgba(34,197,94,0.1)]"
            >
              <CheckCircle2 className="w-8 h-8" />
            </motion.div>

            <div className="space-y-6 w-full mb-10">
              <h2 className="text-2xl font-heading font-bold text-white">Evidence Ready</h2>

              {/* Preview with HUD Frame */}
              <div className="relative rounded-xl overflow-hidden border border-white/5 bg-white/[0.02]">
                <div className="aspect-video w-full flex items-center justify-center overflow-hidden relative">

                  {/* HUD Corners */}
                  <div className="absolute top-4 left-4 w-4 h-4 border-t border-l border-primary/40 z-20" />
                  <div className="absolute top-4 right-4 w-4 h-4 border-t border-r border-primary/40 z-20" />
                  <div className="absolute bottom-4 left-4 w-4 h-4 border-b border-l border-primary/40 z-20" />
                  <div className="absolute bottom-4 right-4 w-4 h-4 border-b border-r border-primary/40 z-20" />

                  {isImage && previewUrl ? (
                    <Image
                      src={previewUrl}
                      alt="Preview"
                      fill
                      className="object-cover"
                    />
                  ) : isVideo && previewUrl ? (
                    <video
                      src={previewUrl}
                      className="w-full h-full object-cover"
                      autoPlay
                      muted
                      loop
                      playsInline
                    />
                  ) : (
                    <div className="flex flex-col items-center gap-3 text-white/10">
                      <FileText className="w-12 h-12" strokeWidth={1} />
                      <span className="text-[10px] font-mono tracking-widest uppercase">DATA_SECURED</span>
                    </div>
                  )}

                  {/* File Metadata HUD */}
                  <div className="absolute inset-x-0 bottom-0 p-5 bg-gradient-to-t from-black/90 to-transparent backdrop-blur-sm border-t border-white/5 flex items-center justify-between">
                    <div className="text-left">
                      <p className="text-xs font-mono text-white/80 truncate max-w-[200px]">
                        {file.name}
                      </p>
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
                onClick={onNewUpload}
                disabled={isStarting}
                className="btn-horizon-outline flex-1 py-4 text-xs disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Reselect File
              </button>
              <button
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
                    <Loader2 className="w-4 h-4 animate-spin" />
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
