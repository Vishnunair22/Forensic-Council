"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { motion, useReducedMotion } from "framer-motion";
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
  const prefersReducedMotion = useReducedMotion();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [audioPreviewUrl, setAudioPreviewUrl] = useState<string | null>(null);
  const { playSound } = useSound();
  const closeBtnRef = useRef<HTMLButtonElement>(null);

  // Revoke object URL on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      if (audioPreviewUrl) URL.revokeObjectURL(audioPreviewUrl);
    };
  }, [audioPreviewUrl]);

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
    // Cross-validate MIME type against file extension to catch spoofed uploads
    const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
    const EXTENSION_MIME_MAP: Record<string, string[]> = {
      jpg: ["image/jpeg"], jpeg: ["image/jpeg"], png: ["image/png"],
      webp: ["image/webp"], gif: ["image/gif"],
      mp4: ["video/mp4"], mov: ["video/quicktime"], avi: ["video/x-msvideo"], webm: ["video/webm"],
      mp3: ["audio/mpeg"], wav: ["audio/wav", "audio/x-wav"], m4a: ["audio/mp4", "audio/x-m4a"],
      pdf: ["application/pdf"],
    };
    const allowedMimesForExt = EXTENSION_MIME_MAP[ext];
    if (allowedMimesForExt && !allowedMimesForExt.includes(file.type)) {
      setError(`File extension ".${ext}" does not match the reported type "${file.type}".`);
      playSound("error");
      return;
    }
    if (isSubmitting) return; // Prevent double-submit
    setIsSubmitting(true);

    // Show audio preview for audio files before submitting
    if (file.type.startsWith("audio/")) {
      if (audioPreviewUrl) URL.revokeObjectURL(audioPreviewUrl);
      setAudioPreviewUrl(URL.createObjectURL(file));
    } else {
      setAudioPreviewUrl(null);
    }

    setError(null);
    playSound("success-chime");
    onFileSelected(file);
    // Note: isSubmitting stays true — modal will close via parent after upload starts
  }, [onFileSelected, playSound, isSubmitting, audioPreviewUrl]);

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
      initial={prefersReducedMotion ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={prefersReducedMotion ? {} : { opacity: 0, transition: { duration: 0.18, ease: "easeIn" } }}
      transition={{ duration: 0.14, ease: "easeOut" }}
      className="fixed inset-0 z-[9999] flex items-center justify-center p-4"
      style={{ background: "rgba(1,2,8,0.88)", backdropFilter: "blur(24px)", WebkitBackdropFilter: "blur(24px)" }}
      onMouseDown={(e) => { if (e.target === e.currentTarget) { playSound("click"); onClose(); } }}
    >
      <div className="relative w-full max-w-lg" onClick={(e) => e.stopPropagation()}>
        <motion.div
          initial={prefersReducedMotion ? false : { opacity: 0, scale: 0.96, y: 16 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={prefersReducedMotion ? {} : { opacity: 0, scale: 0.985, y: 8 }}
          transition={{ duration: 0.26, ease: [0.16, 1, 0.3, 1] }}
          className="relative overflow-hidden rounded-2xl"
          style={{
            background: "rgba(5,9,18,0.97)",
            border: "1px solid rgba(165,200,255,0.10)",
            boxShadow: "0 32px 80px rgba(0,0,0,0.7), 0 0 0 1px rgba(79,142,247,0.06), inset 0 1px 0 rgba(255,255,255,0.05)",
          }}
        >
          {/* Top gradient accent */}
          <div
            className="absolute inset-x-0 top-0 h-px"
            style={{ background: "linear-gradient(90deg, transparent 10%, rgba(79,142,247,0.5) 50%, transparent 90%)" }}
            aria-hidden="true"
          />

          <div className="p-8 sm:p-10 flex flex-col items-center text-center">
            <button
              ref={closeBtnRef}
              type="button"
              onClick={() => { playSound("click"); onClose(); }}
              className="absolute top-5 right-5 w-8 h-8 flex items-center justify-center rounded-xl transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
              style={{ color: "rgba(255,255,255,0.25)", background: "rgba(255,255,255,0.04)" }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.color = "rgba(255,255,255,0.7)"; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.color = "rgba(255,255,255,0.25)"; }}
              aria-label="Close upload dialog"
            >
              <X className="w-4 h-4" />
            </button>

            <p className="text-[9px] font-mono font-bold tracking-[0.28em] uppercase mb-3" style={{ color: "rgba(79,142,247,0.45)" }} aria-hidden="true">
              Evidence Intake
            </p>
            <h2 id="upload-modal-title" className="text-[22px] font-heading font-bold text-white/90 mb-7" style={{ letterSpacing: "-0.02em" }}>
              Upload Evidence
            </h2>

            <div
              data-testid="upload-dropzone"
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              className="w-full rounded-2xl p-10 cursor-pointer group flex flex-col items-center justify-center gap-5 relative overflow-hidden"
              style={{
                border: isDragging
                  ? "1.5px solid rgba(79,142,247,0.45)"
                  : "1.5px dashed rgba(165,200,255,0.10)",
                background: isDragging
                  ? "rgba(79,142,247,0.055)"
                  : "rgba(255,255,255,0.015)",
                boxShadow: isDragging
                  ? "0 0 40px rgba(79,142,247,0.10), inset 0 0 24px rgba(79,142,247,0.04)"
                  : "none",
                transition: "border-color 0.25s ease, background 0.25s ease, box-shadow 0.25s ease",
              }}
            >
              <EnvelopeOpen isDragging={isDragging} />

              <div className="flex flex-col items-center gap-1.5 pointer-events-none">
                <span
                  className="text-[17px] font-heading font-bold transition-colors duration-200"
                  style={{
                    color: isDragging ? "var(--color-primary)" : "rgba(255,255,255,0.70)",
                    letterSpacing: "-0.01em",
                  }}
                >
                  {isDragging ? "Release to Upload" : "Drop Evidence File"}
                </span>
                <p className="text-[13px] text-white/30 max-w-[240px] leading-relaxed">
                  or click to select · images, video, audio, PDF
                </p>
              </div>

              <div className="absolute bottom-3 right-4 text-[8px] font-mono tracking-[0.22em]" style={{ color: "rgba(79,142,247,0.18)" }} aria-hidden="true">
                {isSubmitting ? "UPLOADING..." : "AWAITING_INPUT"}
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
              <p role="alert" className="mt-5 text-[13px] font-semibold" style={{ color: "var(--color-danger)" }}>
                {error}
              </p>
            )}

            {isSubmitting && !error && (
              <p role="status" aria-live="polite" className="mt-5 text-[11px] font-mono animate-pulse" style={{ color: "rgba(79,142,247,0.55)", letterSpacing: "0.18em" }}>
                Preparing secure channel…
              </p>
            )}

            {audioPreviewUrl && (
              <div className="mt-5 w-full" aria-label="Audio preview">
                <p className="text-[9px] font-mono mb-2 text-center tracking-widest" style={{ color: "rgba(255,255,255,0.25)" }}>AUDIO PREVIEW</p>
                <audio
                  controls
                  src={audioPreviewUrl}
                  className="w-full rounded-xl"
                  aria-label="Selected audio file preview"
                />
              </div>
            )}
          </div>
        </motion.div>
      </div>
    </motion.div>,
    document.body
  );
}
