"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { motion, useReducedMotion } from "framer-motion";
import { X, Plus } from "lucide-react";
import { ALLOWED_MIME_TYPES } from "@/lib/constants";
import { useSound } from "@/hooks/useSound";
import { useFocusTrap } from "@/hooks/useFocusTrap";
import { validateEvidenceFile } from "@/lib/fileValidation";

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
  const { playSound } = useSound();
  const dialogRef = useRef<HTMLDivElement>(null);

  const closeModal = useCallback(() => {
    playSound("click");
    onClose();
  }, [playSound, onClose]);

  useFocusTrap(dialogRef, mounted, closeModal);

  // Mount focus guard — focus trap handles first-focus; focus stays in modal
  useEffect(() => {
    setMounted(true);
  }, []);

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
    const error = validateEvidenceFile(file);
    if (error) {
      setError(error);
      playSound("error");
      return;
    }

    if (isSubmitting) return; // Prevent double-submit
    setIsSubmitting(true);

    setError(null);
    playSound("success-chime");
    onFileSelected(file);
    // Note: isSubmitting stays true — modal will close via parent after upload starts
  }, [onFileSelected, playSound, isSubmitting]);

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
      exit={prefersReducedMotion ? {} : { opacity: 0, transition: { duration: 0.12, ease: "easeIn" } }}
      transition={{ duration: 0.14, ease: "easeOut" }}
      className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-black/95"
      onMouseDown={(e) => { if (e.target === e.currentTarget) { playSound("click"); onClose(); } }}
    >
      <div className="relative w-full max-w-lg" onClick={(e) => e.stopPropagation()} ref={dialogRef}>
        <motion.div
          initial={prefersReducedMotion ? false : { opacity: 0, scale: 0.96, y: 16 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={prefersReducedMotion ? {} : { opacity: 0, scale: 0.985, y: 8 }}
          transition={{ duration: 0.26, ease: [0.16, 1, 0.3, 1] }}
          className="relative overflow-hidden bg-[#06090E]"
        >

          <div className="p-8 sm:p-10 flex flex-col items-center text-center">
            <button
              type="button"
              onClick={closeModal}
              className="absolute top-5 right-5 w-8 h-8 flex items-center justify-center rounded-xl bg-white/[0.04] text-white/25 hover:text-white/70 transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
              aria-label="Close upload dialog"
            >
              <X className="w-4 h-4" />
            </button>

            <p className="text-[9px] font-mono font-bold tracking-[0.28em] mb-3" style={{ color: "rgba(79,142,247,0.45)" }} aria-hidden="true">
              Evidence Intake
            </p>
            <h2 id="upload-modal-title" className="text-[22px] font-heading font-bold text-white/90 mb-7" style={{ letterSpacing: "-0.02em" }}>
              Upload Evidence
            </h2>

            <div
              data-testid="upload-dropzone"
              role="button"
              tabIndex={0}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  const input = e.currentTarget.querySelector<HTMLInputElement>("input[type='file']");
                  input?.click();
                }
              }}
              className="w-full p-16 cursor-pointer group flex flex-col items-center justify-center gap-6 relative overflow-hidden transition-colors duration-200"
              style={{
                border: isDragging ? "1px solid #FFFFFF" : "1px solid #333333",
                background: isDragging ? "#111111" : "transparent",
              }}
            >
              <Plus 
                className="w-16 h-16 transition-colors duration-200" 
                style={{ color: isDragging ? "#FFFFFF" : "#555555" }} 
                strokeWidth={1} 
                aria-hidden="true" 
              />

              <div className="flex flex-col items-center gap-2 pointer-events-none">
                <span
                  className="text-xl font-bold transition-colors duration-200 uppercase tracking-widest"
                  style={{ color: isDragging ? "#FFFFFF" : "#888888" }}
                >
                  {isDragging ? "Drop Evidence" : "Select Evidence"}
                </span>
                <p id="upload-file-help" className="text-sm text-slate-500 max-w-[260px] leading-relaxed">
                  images, video, audio (max 50MB)
                </p>
              </div>



              <input
                type="file"
                id="evidence-file-input"
                aria-label="Choose evidence file"
                aria-describedby={error ? "upload-file-help upload-error" : "upload-file-help"}
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
              <p id="upload-error" role="alert" className="mt-5 text-[13px] font-semibold" style={{ color: "var(--color-danger)" }}>
                {error}
              </p>
            )}

            {isSubmitting && !error && (
              <p role="status" aria-live="polite" className="mt-5 text-[11px] font-mono animate-pulse" style={{ color: "rgba(79,142,247,0.55)", letterSpacing: "0.18em" }}>
                Preparing secure channel…
              </p>
            )}
          </div>
        </motion.div>
      </div>
    </motion.div>,
    document.body
  );
}
