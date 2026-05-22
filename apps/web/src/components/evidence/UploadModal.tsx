"use client";

import { useState, useCallback } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { X, Plus } from "lucide-react";
import { ALLOWED_MIME_TYPES } from "@/lib/constants";
import { useSound } from "@/hooks/useSound";
import { validateEvidenceFile } from "@/lib/fileValidation";

export interface UploadModalProps {
  onClose: () => void;
  onFileSelected: (file: File) => void;
}

export function UploadModal({ onClose, onFileSelected }: UploadModalProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const prefersReducedMotion = useReducedMotion();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { playSound } = useSound();

  const closeModal = useCallback(() => {
    playSound("click");
    onClose();
  }, [playSound, onClose]);

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
    const validationError = validateEvidenceFile(file);
    if (validationError) {
      setError(validationError);
      playSound("error");
      return;
    }
    if (isSubmitting) return;
    setIsSubmitting(true);
    setError(null);
    playSound("success-chime");
    onFileSelected(file);
  }, [onFileSelected, playSound, isSubmitting]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) selectFile(file);
  }, [selectFile]);

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
        className="absolute top-6 right-6 w-8 h-8 flex items-center justify-center fc-text-faint hover:text-white transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 rounded-full"
        aria-label="Close upload dialog"
      >
        <X className="w-5 h-5" />
      </button>

      <div className="mb-8">
        <p className="fc-eyebrow fc-text-muted mb-2" aria-hidden="true">
          Evidence Intake
        </p>
        <h2 className="text-3xl font-heading font-bold fc-text-primary">
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
        className={`w-full py-16 px-8 cursor-pointer group flex flex-col items-center justify-center gap-4 relative transition-all duration-150 fc-upload-zone ${
          isDragging
            ? "border-primary"
            : ""
        }`}
      >
        <Plus
          className={`w-12 h-12 transition-colors duration-150 ${
            isDragging ? "text-primary" : "text-white/40 group-hover:text-white/60"
          }`}
          strokeWidth={1}
          aria-hidden="true"
        />

        <div className="flex flex-col items-center gap-2 pointer-events-none text-center">
          <span
            className={`text-lg font-bold transition-colors duration-150 tracking-wide ${
              isDragging ? "text-primary" : "fc-text-secondary group-hover:text-white"
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
        <div className="mt-6 p-4 border border-[var(--color-danger)]/20 bg-[var(--color-danger)]/5 rounded-2xl">
          <p id="upload-error" role="alert" className="text-sm font-mono fc-text-danger">
            {error}
          </p>
        </div>
      )}

      {isSubmitting && !error && (
        <div className="mt-6 flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
          <p role="status" aria-live="polite" className="text-xs font-mono tracking-widest text-primary/80">
            Preparing secure channel...
          </p>
        </div>
      )}
    </motion.div>
  );
}
