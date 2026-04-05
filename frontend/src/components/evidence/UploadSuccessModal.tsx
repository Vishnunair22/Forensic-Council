"use client";

import { useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { RefreshCw, ArrowRight, FileImage, FileAudio, FileVideo, FileText } from "lucide-react";

const overlayVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.25 } },
  exit: { opacity: 0, transition: { duration: 0.2 } },
};

const scaleIn = {
  hidden: { opacity: 0, scale: 0.85 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: { duration: 0.3, ease: [0.34, 1.56, 0.64, 1] as const },
  },
  exit: { opacity: 0, scale: 0.85, transition: { duration: 0.2 } },
};

interface UploadSuccessModalProps {
  file: File;
  onNewUpload: () => void;
  onStartAnalysis: () => void;
}

export function UploadSuccessModal({
  file,
  onNewUpload,
  onStartAnalysis,
}: UploadSuccessModalProps) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [hasError, setHasError] = useState(false);
  const modalRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      return;
    }
    const isMedia =
      file.type.startsWith("image/") ||
      file.type.startsWith("video/") ||
      /\.(jpe?g|png|gif|bmp|webp|jfif|mp4|webm|mov|ogg)$/i.test(file.name);
    if (isMedia) {
      const reader = new FileReader();
      reader.onloadend = () => setPreviewUrl(reader.result as string);
      reader.onerror = () => setHasError(true);
      reader.readAsDataURL(file);
    } else {
      setPreviewUrl(null);
    }
  }, [file]);

  useEffect(() => {
    previousFocusRef.current = document.activeElement as HTMLElement;
    if (modalRef.current) {
      const focusable = modalRef.current.querySelector<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      focusable?.focus();
    }
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onStartAnalysis();
      }
      if (e.key === "Tab") {
        const focusableElements = modalRef.current?.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        if (!focusableElements || focusableElements.length === 0) return;
        const firstFocusable = focusableElements[0];
        const lastFocusable = focusableElements[focusableElements.length - 1];
        if (e.shiftKey) {
          if (document.activeElement === firstFocusable) {
            e.preventDefault();
            lastFocusable.focus();
          }
        } else {
          if (document.activeElement === lastFocusable) {
            e.preventDefault();
            firstFocusable.focus();
          }
        }
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      previousFocusRef.current?.focus();
    };
  }, [onStartAnalysis]);

  const isVideo =
    file.type.startsWith("video/") || /\.(mp4|webm|mov|ogg)$/i.test(file.name);
  const FileTypeIcon = file.type.startsWith("image/")
    ? FileImage
    : file.type.startsWith("audio/")
      ? FileAudio
      : isVideo
        ? FileVideo
        : FileText;

  return (
    <motion.div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4 backdrop-blur-2xl"
      style={{ background: "rgba(0,3,7,0.85)" }}
      variants={overlayVariants}
      initial="hidden"
      animate="visible"
      exit="exit"
      role="dialog"
      aria-modal="true"
      aria-labelledby="upload-success-title"
    >
      <motion.div
        ref={modalRef}
        className="relative w-full max-w-sm overflow-hidden rounded-[3rem] p-10 bg-[#0A0D10]/80 border border-white/10 shadow-[0_40px_100px_rgba(0,0,0,0.8),inset_0_0_20px_rgba(34,211,238,0.05)]"
        variants={scaleIn}
        initial="hidden"
        animate="visible"
        exit="exit"
      >
        {/* Dynamic Background Glows */}
        <div className="absolute top-0 right-0 w-64 h-64 bg-cyan-500/10 blur-[100px] rounded-full -mr-20 -mt-20 pointer-events-none" />
        <div className="absolute bottom-0 left-0 w-64 h-64 bg-indigo-500/10 blur-[100px] rounded-full -ml-20 -mb-20 pointer-events-none" />

        <motion.div
          className="w-32 h-32 rounded-[2.5rem] mx-auto mb-10 overflow-hidden flex items-center justify-center relative z-10 border-2 border-white/10 bg-white/[0.04] shadow-2xl"
          animate={{
            scale: [1, 1.05, 1],
            rotate: [0, 1, 0, -1, 0],
          }}
          transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
        >
          {previewUrl && !hasError ? (
            isVideo ? (
              <video
                key={previewUrl}
                src={previewUrl}
                className="w-full h-full object-cover"
                muted
                loop
                autoPlay
                playsInline
                onError={() => setHasError(true)}
                aria-hidden="true"
              />
            ) : (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img
                key={previewUrl}
                src={previewUrl}
                alt={`Evidence preview: ${file.name}`}
                className="w-full h-full object-cover"
                onError={() => setHasError(true)}
              />
            )
          ) : (
            <div className="flex flex-col items-center gap-3">
              <div className="p-4 rounded-3xl bg-cyan-500/10 border border-cyan-500/20">
                <FileTypeIcon
                  className="w-10 h-10 text-cyan-400"
                  aria-hidden="true"
                />
              </div>
            </div>
          )}
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2, duration: 0.5, ease: "easeOut" }}
          className="relative z-10"
        >
          <div className="flex flex-col items-center mb-12">
            <div className="inline-flex items-center gap-3 mb-6 px-5 py-2 rounded-full bg-emerald-500/10 border border-emerald-500/20 backdrop-blur-sm">
              <motion.div
                className="w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-[0_0_15px_rgba(52,211,153,0.6)]"
                animate={{ opacity: [1, 0.5, 1] }}
                transition={{ duration: 2, repeat: Infinity }}
              />
              <span className="text-[12px] font-black text-emerald-400 tracking-[0.15em] uppercase">
                Securely Uploaded
              </span>
            </div>
            
            <h3 id="upload-success-title" className="text-white text-xl font-black truncate max-w-full px-4 mb-3 tracking-tight font-sans">
              {file.name}
            </h3>
            
            <div className="flex items-center gap-4 text-[12px] font-mono font-bold text-white/30 uppercase tracking-[0.2em] bg-white/[0.03] px-4 py-1 rounded-lg">
              <span>{file.type.split("/")[1] || "BINARY"}</span>
              <span className="w-1.5 h-1.5 rounded-full bg-white/20" />
              <span>{(file.size / (1024 * 1024)).toFixed(2)} MB</span>
            </div>
          </div>

          <div className="flex gap-4">
            <button
              onClick={onNewUpload}
              className="group relative flex-1"
            >
              <div className="absolute inset-0 bg-white/5 rounded-full blur-md opacity-0 group-hover:opacity-100 transition-opacity" />
              <div className="relative flex items-center justify-center gap-2 py-4 px-6 rounded-full border border-white/10 bg-white/5 text-white font-bold hover:bg-white/10 hover:border-white/20 transition-all active:scale-95">
                <RefreshCw className="w-4 h-4 group-hover:rotate-180 transition-transform duration-500" />
                <span className="text-sm">Reset</span>
              </div>
            </button>

            <button
              onClick={onStartAnalysis}
              className="group relative flex-[1.4]"
            >
              <div className="absolute inset-0 bg-cyan-500/20 rounded-full blur-xl opacity-0 group-hover:opacity-100 transition-opacity animate-pulse" />
              <div className="relative flex items-center justify-center gap-2 py-4 px-6 rounded-full bg-cyan-500 text-black font-black hover:bg-cyan-400 transition-all shadow-[0_10px_30px_rgba(34,211,238,0.3)] active:scale-95 active:shadow-inner">
                <span className="text-sm">Analyse</span>
                <ArrowRight className="w-5 h-5 group-hover:translate-x-1.5 transition-transform" />
              </div>
            </button>
          </div>
        </motion.div>
      </motion.div>
    </motion.div>
  );
}
