"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { motion } from "framer-motion";
import { X } from "lucide-react";
import { ALLOWED_MIME_TYPES, MAX_UPLOAD_SIZE_BYTES } from "@/lib/constants";
import { useSound } from "@/hooks/useSound";

// Envelope icon — shows open state with drag-reactive document card
function EnvelopeOpen({ isDragging }: { isDragging: boolean }) {
  return (
    <div className="relative flex h-24 w-24 items-center justify-center" aria-hidden="true">
      {/* Rotating dashed ring — CSS animation, no framer-motion overhead */}
      <div className="absolute inset-0 rounded-full border border-primary/[0.18] border-dashed [animation:spin_24s_linear_infinite]" />
      <div className="absolute inset-2 rounded-full border border-primary/[0.08]" />

      <div className="relative w-16 h-12">
        <svg viewBox="0 0 64 48" className="w-full h-full">
          <defs>
            <linearGradient id="envBody" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#1e293b" />
              <stop offset="100%" stopColor="#0f172a" />
            </linearGradient>
            <linearGradient id="envFlap" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#334155" />
              <stop offset="100%" stopColor="#1e293b" />
            </linearGradient>
          </defs>

          {/* Envelope body */}
          <path
            d="M2 12 L2 42 Q2 46 6 46 L58 46 Q62 46 62 42 L62 12 Q62 8 58 8 L6 8 Q2 8 2 12Z"
            fill="url(#envBody)"
            stroke="#475569"
            strokeWidth="1"
          />
          <path d="M2 12 L32 28 L62 12" fill="none" stroke="#475569" strokeWidth="1" />

          {/* Flap — open position */}
          <path
            d="M2 8 L32 26 L62 8"
            fill="url(#envFlap)"
            stroke="#64748b"
            strokeWidth="0.5"
          />

          {/* Document card — rises on drag */}
          <motion.rect
            x="10" y="22" width="44" height="18" rx="1"
            fill="#f8fafc"
            animate={{ y: isDragging ? 0 : 8, opacity: isDragging ? 1 : 0.6 }}
            transition={{ duration: 0.28, ease: "easeOut" }}
          />
          <motion.path
            d="M16 28 L28 36"
            stroke="#94a3b8" strokeWidth="1.5"
            animate={{ opacity: isDragging ? 1 : 0.35 }}
            transition={{ duration: 0.2 }}
          />
          <motion.path
            d="M36 28 L48 36"
            stroke="#94a3b8" strokeWidth="1.5"
            animate={{ opacity: isDragging ? 1 : 0.35 }}
            transition={{ duration: 0.2, delay: 0.04 }}
          />
        </svg>
      </div>
    </div>
  );
}

export interface UploadModalProps {
  onClose: () => void;
  onFileSelected: (file: File) => void;
}

export function UploadModal({ onClose, onFileSelected }: UploadModalProps) {
  const [mounted, setMounted] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { playSound } = useSound();
  const closeBtnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    setMounted(true);
    // Move focus into the dialog after mount
    closeBtnRef.current?.focus();
  }, []);

  // Escape key closes the dialog
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") { playSound("click"); onClose(); }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, playSound]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const selectFile = useCallback((file: File) => {
    if (file.size > MAX_UPLOAD_SIZE_BYTES) {
      setError("File must be 50MB or smaller.");
      playSound("error");
      return;
    }
    if (!ALLOWED_MIME_TYPES.has(file.type)) {
      setError(`File type "${file.type || "unknown"}" is not supported.`);
      playSound("error");
      return;
    }
    setError(null);
    playSound("success-chime");
    onFileSelected(file);
  }, [onFileSelected, playSound]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) selectFile(file);
  }, [selectFile]);

  if (!mounted) return null;

  return createPortal(
    <motion.div
      role="dialog"
      aria-modal="true"
      aria-labelledby="upload-modal-title"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: 0.18, ease: "easeIn" } }}
      transition={{ duration: 0.14, ease: "easeOut" }}
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-[#020617]/85 backdrop-blur-xl p-4"
      onMouseDown={(e) => { if (e.target === e.currentTarget) { playSound("click"); onClose(); } }}
    >
      <div className="relative w-full max-w-xl" onClick={(e) => e.stopPropagation()}>
        <motion.div
          initial={{ opacity: 0, scale: 0.97, y: 12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.985, y: 6 }}
          transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
          className="horizon-card p-1 relative overflow-hidden"
        >
          <div
            className="rounded-[inherit] p-10 flex flex-col items-center text-center"
            style={{ background: "radial-gradient(ellipse 80% 50% at 50% 0%, rgba(59,130,246,0.05) 0%, #020617 60%)" }}
          >
            <button
              ref={closeBtnRef}
              type="button"
              onClick={() => { playSound("click"); onClose(); }}
              className="absolute top-6 right-6 text-white/25 hover:text-white/70 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 rounded"
              aria-label="Close upload dialog"
            >
              <X className="w-5 h-5" />
            </button>

            <p className="text-[10px] font-mono font-bold tracking-[0.25em] text-primary/50 uppercase mb-3" aria-hidden="true">
              Evidence Intake
            </p>
            <h2 id="upload-modal-title" className="text-2xl font-heading font-bold text-white mb-8">
              Upload Evidence
            </h2>

            <div
              data-testid="upload-dropzone"
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              className={`w-full border border-dashed rounded-2xl p-12 transition-[border-color,background-color,box-shadow] duration-300 cursor-pointer group flex flex-col items-center justify-center gap-6 relative overflow-hidden ${
                isDragging
                  ? "border-primary bg-primary/[0.06] shadow-[0_0_50px_rgba(59,130,246,0.12),inset_0_0_30px_rgba(59,130,246,0.04)]"
                  : "border-white/[0.08] hover:border-primary/25 hover:bg-white/[0.018]"
              }`}
            >
              <EnvelopeOpen isDragging={isDragging} />

              <div className="flex flex-col items-center gap-2 pointer-events-none">
                <span className={`text-xl font-heading font-bold tracking-tight transition-colors duration-200 ${isDragging ? "text-primary" : "text-white/75 group-hover:text-white"}`}>
                  {isDragging ? "Release Payload" : "Drop Evidence File"}
                </span>
                <p className="text-sm font-medium text-white/35 max-w-[240px] leading-relaxed">
                  Select a forensic file for multi-agent neural verification.
                </p>
              </div>

              <div className="absolute bottom-4 right-4 text-[9px] font-mono text-primary/20 tracking-widest" aria-hidden="true">
                WAITING_FOR_DATA
              </div>

              <input
                type="file"
                aria-label="Upload evidence file"
                className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                accept={Array.from(ALLOWED_MIME_TYPES).join(",")}
                onClick={(e) => { (e.target as HTMLInputElement).value = ""; }}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) selectFile(file);
                }}
              />
            </div>

            {error && (
              <p role="alert" className="mt-4 text-sm font-semibold text-[var(--color-danger)]">
                {error}
              </p>
            )}
          </div>
        </motion.div>
      </div>
    </motion.div>,
    document.body
  );
}
