"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { motion } from "framer-motion";
import { X, UploadCloud, FileImage, FileVideo, FileAudio, FileText } from "lucide-react";

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

interface UploadModalProps {
  onClose: () => void;
  onFileSelected: (f: File) => void;
}

export function UploadModal({ onClose, onFileSelected }: UploadModalProps) {
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const modalRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  const handleFile = useCallback(
    (f: File) => {
      onFileSelected(f);
    },
    [onFileSelected],
  );

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
        onClose();
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
  }, [onClose]);

  return (
    <motion.div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.6)", backdropFilter: "blur(12px)" }}
      variants={overlayVariants}
      initial="hidden"
      animate="visible"
      exit="exit"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="upload-modal-title"
    >
      <motion.div
        ref={modalRef}
        className="relative w-full max-w-lg"
        variants={scaleIn}
        initial="hidden"
        animate="visible"
        exit="exit"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="rounded-3xl overflow-hidden glass-panel">
          {/* Header accent bar */}
          <div
            className="relative w-full h-20 origin-top"
            style={{
              background:
                "linear-gradient(135deg, rgba(34,211,238,0.15) 0%, rgba(79,70,229,0.12) 100%)",
              clipPath: "polygon(0 0, 50% 100%, 100% 0)",
              transform: "rotateX(180deg)",
            }}
          />

          <div className="relative p-10 pt-6 -mt-2">
            <div className="absolute -top-24 -right-24 w-48 h-48 bg-cyan-500/10 blur-[80px] pointer-events-none" />
            <button
              onClick={onClose}
              className="absolute top-6 right-6 p-2 rounded-xl cursor-pointer hover:bg-white/5 transition-colors border border-white/5"
              aria-label="Close upload modal"
            >
              <X className="w-5 h-5 text-white/40" />
            </button>

            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15, duration: 0.35 }}
            >
              <div className="mb-8">
                <h3 id="upload-modal-title" className="text-2xl font-bold text-white tracking-tight">
                  Upload Evidence
                </h3>
              </div>

              <motion.div
                role="button"
                tabIndex={0}
                aria-label="Upload evidence — click or press Enter to browse, or drag and drop a file"
                className="group relative rounded-2xl border-2 border-dashed p-12 text-center cursor-pointer overflow-hidden"
                style={{
                  borderColor: isDragging
                    ? "rgba(34,211,238,0.5)"
                    : "rgba(255,255,255,0.08)",
                  background: isDragging
                    ? "rgba(34,211,238,0.05)"
                    : "rgba(255,255,255,0.02)",
                }}
                whileHover={{
                  borderColor: "rgba(34,211,238,0.3)",
                  background: "rgba(34,211,238,0.03)",
                }}
                transition={{ duration: 0.2 }}
                onDragOver={(e) => {
                  e.preventDefault();
                  setIsDragging(true);
                }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setIsDragging(false);
                  const f = e.dataTransfer.files[0];
                  if (f) handleFile(f);
                }}
                onClick={() => fileInputRef.current?.click()}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    fileInputRef.current?.click();
                  }
                }}
              >
                <div className="absolute inset-0 bg-gradient-to-b from-cyan-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
                <div className="relative z-10">
                  <motion.div
                    className="w-16 h-16 rounded-2xl bg-cyan-500/10 flex items-center justify-center mx-auto mb-5 border border-cyan-500/20"
                    whileHover={{ scale: 1.1 }}
                    transition={{ type: "spring", stiffness: 400, damping: 17 }}
                  >
                    <UploadCloud className="w-8 h-8 text-cyan-400" />
                  </motion.div>
                  <p className="text-lg font-semibold text-white mb-2">
                    Drop file here or{" "}
                    <span className="text-cyan-400 underline underline-offset-4 decoration-cyan-400/30">
                      browse
                    </span>
                  </p>
                  <div className="flex items-center justify-center gap-3 opacity-40">
                    <FileImage className="w-4 h-4" />
                    <FileVideo className="w-4 h-4" />
                    <FileAudio className="w-4 h-4" />
                    <FileText className="w-4 h-4" />
                  </div>
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  className="hidden"
                  accept="image/*,audio/*,video/*"
                  aria-label="Select evidence file"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) handleFile(f);
                  }}
                />
              </motion.div>

              <div className="mt-8 flex flex-col gap-2">
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-500" />
                  <p className="text-sm font-medium text-white/60">
                    Supported: Image, Video, Audio, Document
                  </p>
                </div>
                <p className="text-xs text-white/30 ml-3.5">
                  Maximum file size: 50 MB &middot; SHA-256 integrity check
                  performed automatically.
                </p>
              </div>
            </motion.div>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}
