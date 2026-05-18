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
          initial={prefersReducedMotion ? false : { opacity: 0, scale: 0.98, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={prefersReducedMotion ? {} : { opacity: 0, scale: 0.99, y: 5 }}
          transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
          className="relative overflow-hidden rounded-2xl border border-border-muted"
          style={{ background: "rgba(255, 255, 255, 0.015)", backdropFilter: "blur(24px)" }}
        >
          <div className="p-8 sm:p-10 flex flex-col text-left">
            <button
              type="button"
              onClick={closeModal}
              className="absolute top-6 right-6 w-8 h-8 flex items-center justify-center fc-text-faint hover:fc-text-primary transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 rounded"
              aria-label="Close upload dialog"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="mb-8">
              <p className="fc-eyebrow fc-text-faint mb-2" aria-hidden="true">
                Evidence Intake
              </p>
              <h2 id="upload-modal-title" className="text-3xl font-heading font-bold text-white">
                Upload Evidence
              </h2>
            </div>

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
              className={`w-full py-16 px-8 cursor-pointer group flex flex-col items-center justify-center gap-4 relative transition-all duration-300 border-2 border-dashed rounded-2xl ${
                isDragging 
                  ? "bg-transparent border-primary shadow-[0_0_25px_rgba(79,142,247,0.15)]" 
                  : "border-white/10 bg-transparent hover:border-white/20"
              }`}
            >
              <Plus 
                className={`w-12 h-12 transition-colors duration-200 ${
                  isDragging ? "text-primary" : "text-white/40 group-hover:text-white/60"
                }`} 
                strokeWidth={1} 
                aria-hidden="true" 
              />

              <div className="flex flex-col items-center gap-2 pointer-events-none text-center">
                <span
                  className={`text-lg font-bold transition-colors duration-200 uppercase tracking-widest ${
                    isDragging ? "text-primary" : "text-white/80 group-hover:text-white"
                  }`}
                >
                  {isDragging ? "Drop Evidence" : "Select Evidence"}
                </span>
                <p id="upload-file-help" className="text-sm font-mono fc-text-muted max-w-[260px]">
                  images, video, audio (max 50MB)
                </p>
              </div>

              <input
                type="file"
                id="evidence-file-input"
                aria-label="Upload evidence file"
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
              <div className="mt-6 p-4 border border-[var(--color-danger)]/20 bg-[var(--color-danger)]/5 rounded-lg">
                <p id="upload-error" role="alert" className="text-[13px] font-mono text-[var(--color-danger)]">
                  {error}
                </p>
              </div>
            )}

            {isSubmitting && !error && (
              <div className="mt-6 flex items-center gap-3">
                <div className="w-2 h-2 bg-primary animate-pulse" />
                <p role="status" aria-live="polite" className="text-xs font-mono tracking-widest text-primary/80 uppercase">
                  Preparing secure channel...
                </p>
              </div>
            )}
          </div>
        </motion.div>
      </div>
    </motion.div>,
    document.body
  );
}
