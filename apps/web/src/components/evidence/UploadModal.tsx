"use client";

import { useState, useCallback } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { X, CloudUpload } from "lucide-react";
import { ALLOWED_MIME_TYPES } from "@/lib/constants";
import { useSound } from "@/hooks/useSound";
import { validateEvidenceFile, ALLOWED_EXTENSIONS } from "@/lib/fileValidation";

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
    // Ignore if the cursor moved onto a child element — dragLeave bubbles from children.
    if (e.currentTarget.contains(e.relatedTarget as Node)) return;
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
    setTimeout(() => {
      onFileSelected(file);
    }, 600);
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
      {/* Close button */}
      <button
        type="button"
        onClick={closeModal}
        className="absolute top-5 right-5 w-10 h-10 flex items-center justify-center fc-text-muted hover:fc-text-primary fc-transition fc-focus-ring rounded-full cursor-pointer"
        aria-label="Close upload dialog"
      >
        <X className="w-5 h-5" aria-hidden="true" />
      </button>

      {/* Header */}
      <div className="mb-8">
        <p className="fc-eyebrow fc-text-muted mb-2" aria-hidden="true">
          Evidence Intake
        </p>
        <h2 className="text-xl lg:text-2xl font-heading font-bold fc-text-primary">
          Upload Evidence
        </h2>
      </div>

      {/* Drop zone */}
      <div
        data-testid="upload-dropzone"
        role="button"
        tabIndex={0}
        aria-label="Upload evidence file. Drag and drop or press Enter to browse files."
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
        className={`fc-upload-zone w-full py-16 px-8 group flex flex-col items-center justify-center gap-4 relative transition-all duration-[160ms] ${
          isDragging ? "!border-solid !border-primary !bg-primary/5 cursor-copy" : "cursor-pointer"
        }`}
      >
        <CloudUpload
          className={`w-8 h-8 transition-colors duration-[160ms] ${
            isDragging ? "text-primary" : "fc-text-muted group-hover:fc-text-primary"
          }`}
          strokeWidth={1.5}
          aria-hidden="true"
        />

        <div className="flex flex-col items-center gap-2 pointer-events-none text-center">
          <span
            className={`text-lg font-bold transition-colors duration-[160ms] tracking-wide ${
              isDragging ? "text-primary" : "fc-text-secondary group-hover:fc-text-primary"
            }`}
          >
            {isDragging ? "Drop Evidence" : "Select Evidence"}
          </span>
          <p id="upload-file-help" className="text-sm fc-text-muted max-w-[260px]">
            images, video, audio (max 50MB)
          </p>
        </div>

        <input
          type="file"
          id="evidence-file-input"
          tabIndex={-1}
          aria-label="Upload evidence file"
          aria-describedby={error ? "upload-file-help upload-error" : "upload-file-help"}
          className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
          accept={[...ALLOWED_MIME_TYPES, ...ALLOWED_EXTENSIONS].join(",")}
          onClick={(e) => { (e.target as HTMLInputElement).value = ""; }}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) selectFile(file);
          }}
        />
      </div>

      {/* Error message */}
      {error && (
        <div
          className="mt-6 p-4 rounded-2xl"
          style={{
            border: "1px solid rgba(var(--color-danger-rgb), 0.20)",
            background: "rgba(var(--color-danger-rgb), 0.05)",
          }}
        >
          <p id="upload-error" role="alert" className="text-sm fc-text-danger">
            {error}
          </p>
        </div>
      )}

      {/* Submitting state */}
      {isSubmitting && !error && (
        <div className="mt-6 flex items-center gap-3">
          <div
            className="w-4 h-4 rounded-full border-2 border-white/20 border-t-primary animate-spin flex-shrink-0"
            role="status"
            aria-label="Processing"
          />
          <p aria-live="polite" className="text-xs fc-text-muted">
            Preparing secure channel…
          </p>
        </div>
      )}
    </motion.div>
  );
}
