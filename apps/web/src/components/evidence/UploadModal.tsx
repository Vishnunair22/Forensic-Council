"use client";

import { useState, useCallback, useRef } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { X, CloudUpload } from "lucide-react";
import { ALLOWED_MIME_TYPES } from "@/lib/constants";
import { useSound } from "@/hooks/useSound";
import { validateEvidenceFile, ALLOWED_EXTENSIONS } from "@/lib/fileValidation";
import { TRANSITION_FAST } from "@/lib/animations";

export interface UploadModalProps {
  onClose: () => void;
  onFileSelected: (file: File) => void;
  authError?: string | null;
}

export function UploadModal({ onClose, onFileSelected, authError }: UploadModalProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const prefersReducedMotion = useReducedMotion();
  const { playSound } = useSound();
  const isSubmittingRef = useRef(false);

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
    if (isSubmittingRef.current) return;
    isSubmittingRef.current = true;
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

  return (
    <motion.div
      initial={prefersReducedMotion ? false : { opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={prefersReducedMotion ? {} : { opacity: 0, y: 4 }}
      transition={TRANSITION_FAST}
      className="p-8 sm:p-10 flex flex-col text-left"
    >
      <button
        type="button"
        onClick={closeModal}
        className="absolute top-5 right-5 w-10 h-10 flex items-center justify-center fc-text-muted hover:fc-text-primary hover:bg-white/5 border border-transparent hover:border-white/10 fc-transition fc-focus-ring rounded-full cursor-pointer"
        aria-label="Close upload dialog"
      >
        <X className="w-5 h-5" aria-hidden="true" />
      </button>

      <div className="mb-8 border-b border-white/5 pb-4">
        <div className="flex items-center gap-2 mb-2">
          <div className="w-2 h-2 rounded-full bg-primary animate-pulse" aria-hidden="true" />
          <p className="text-xs font-mono font-semibold tracking-widest text-primary uppercase" aria-hidden="true">
            Node: Alpha-7 Intake
          </p>
        </div>
        <h2 className="text-2xl lg:text-3xl font-heading font-bold fc-text-primary tracking-tight">
          Evidence Acquisition
        </h2>
      </div>

      {authError && (
        <div
          className="mb-6 p-4 rounded-xl border border-red-500/20 bg-red-500/5 text-sm fc-text-danger"
          role="alert"
        >
          <strong>Authentication Warning:</strong> {authError}. You can still select files, but starting the analysis may fail.
        </div>
      )}

      <motion.div
        data-testid="upload-dropzone"
        role="button"
        tabIndex={0}
        aria-label="Evidence dropzone. Drag and drop or press Enter to browse files."
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            document.getElementById("evidence-file-input")?.click();
          }
        }}
        animate={isDragging ? "active" : "idle"}
        variants={{
          idle: {
            scale: 1,
            borderColor: "rgba(var(--color-primary-rgb), 0.2)",
            backgroundColor: "rgba(var(--color-primary-rgb), 0.02)",
          },
          active: {
            scale: 1.02,
            borderColor: "rgba(var(--color-primary-rgb), 0.8)",
            backgroundColor: "rgba(var(--color-primary-rgb), 0.08)",
          },
        }}
        transition={{ type: "spring", stiffness: 300, damping: 20 }}
        className="fc-upload-zone w-full py-16 px-8 group flex flex-col items-center justify-center gap-4 relative overflow-hidden rounded-2xl border border-dashed focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background cursor-pointer"
      >
        <AnimatePresence>
          {isDragging && (
            <motion.div
              initial={{ top: "0%", opacity: 0 }}
              animate={{ top: ["0%", "100%", "0%"], opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ top: { duration: 2, repeat: Infinity, ease: "linear" }, opacity: { duration: 0.2 } }}
              className="absolute left-0 right-0 h-[2px] bg-primary z-10 pointer-events-none"
              aria-hidden="true"
            />
          )}
        </AnimatePresence>

        <CloudUpload
          className={`w-10 h-10 transition-colors duration-300 relative z-20 ${
            isDragging ? "text-primary drop-shadow-[0_0_8px_rgba(var(--color-primary-rgb),0.5)]" : "fc-text-muted group-hover:fc-text-primary"
          }`}
          strokeWidth={1.2}
          aria-hidden="true"
        />

        <div className="flex flex-col items-center gap-2 pointer-events-none text-center relative z-20">
          <span className={`text-lg font-bold tracking-widest uppercase transition-colors duration-300 ${
              isDragging ? "text-primary" : "fc-text-secondary group-hover:fc-text-primary"
            }`}
          >
            {isDragging ? "Initiate Transfer" : "Select Evidence"}
          </span>
          <p id="upload-file-help" className="text-xs font-mono fc-text-muted opacity-70 uppercase tracking-wider">
            Supported: IMG, VID, AUD // Max 50MB
          </p>
        </div>

        <input
          type="file"
          id="evidence-file-input"
          aria-label="Upload evidence file"
          tabIndex={-1}
          className="absolute inset-0 h-full w-full cursor-pointer opacity-0 z-30"
          accept={[...ALLOWED_MIME_TYPES, ...ALLOWED_EXTENSIONS].join(",")}
          onClick={(e) => { (e.target as HTMLInputElement).value = ""; }}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) selectFile(file);
          }}
        />
      </motion.div>

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
    </motion.div>
  );
}
