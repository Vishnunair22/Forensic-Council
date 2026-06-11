"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { X, CloudUpload, Volume2, VolumeX } from "lucide-react";
import { ALLOWED_MIME_TYPES } from "@/lib/constants";
import { useSound } from "@/hooks/useSound";
import { validateEvidenceFile, ALLOWED_EXTENSIONS } from "@/lib/fileValidation";
import { TRANSITION_FAST } from "@/lib/animations";

export interface UploadModalProps {
  onClose: () => void;
  onFileSelected: (file: File) => void | Promise<void>;
  authError?: string | null;
}

export function UploadModal({ onClose, onFileSelected, authError }: UploadModalProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSecuring, setIsSecuring] = useState(false);
  const prefersReducedMotion = useReducedMotion();
  const { playSound, isMuted, toggleMute } = useSound();
  const isSubmittingRef = useRef(false);
  const dropzoneRef = useRef<HTMLDivElement>(null);

  // Land focus on the dropzone (the primary action) when this view mounts —
  // both on first open and when returning here via "Reselect". Deferred a frame
  // so it wins against Radix's default focus-first-element behaviour on open.
  useEffect(() => {
    const raf = requestAnimationFrame(() => dropzoneRef.current?.focus());
    return () => cancelAnimationFrame(raf);
  }, []);

  const closeModal = useCallback(() => {
    playSound("envelope-close");
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

  const selectFile = useCallback(async (file: File) => {
    const validationError = validateEvidenceFile(file);
    if (validationError) {
      setError(validationError);
      setIsSecuring(false);
      playSound("error");
      return;
    }
    if (isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    setError(null);
    setIsSecuring(true);

    try {
      await onFileSelected(file);
      isSubmittingRef.current = false;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not prepare file.");
      setIsSecuring(false);
      isSubmittingRef.current = false;
      playSound("error");
    }
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
      initial={prefersReducedMotion ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={prefersReducedMotion ? {} : { opacity: 0, y: 8 }}
      transition={TRANSITION_FAST}
      className="p-8 sm:p-10 flex flex-col text-left"
    >
      {/* Sound mute toggle — top-left, unobtrusive */}
      <button
        type="button"
        onClick={() => toggleMute()}
        className="absolute top-4 left-4 w-9 h-9 flex items-center justify-center fc-text-muted hover:text-foreground hover:bg-white/5 border border-transparent hover:border-white/8 fc-transition fc-focus-ring rounded-full cursor-pointer opacity-50 hover:opacity-100"
        aria-label={isMuted ? "Unmute sounds" : "Mute sounds"}
      >
        {isMuted
          ? <VolumeX className="w-4 h-4" aria-hidden="true" />
          : <Volume2 className="w-4 h-4" aria-hidden="true" />
        }
      </button>

      <button
        type="button"
        onClick={closeModal}
        className="absolute top-4 right-4 w-11 h-11 flex items-center justify-center fc-text-muted hover:text-foreground hover:bg-white/5 border border-transparent hover:border-white/10 fc-transition fc-focus-ring rounded-full cursor-pointer"
        aria-label="Close upload dialog"
      >
        <X className="w-5 h-5" aria-hidden="true" />
      </button>

      <div className="mb-8 border-b border-white/5 pb-4">
        <div className="flex items-center gap-2 mb-2">
          {/* w-1.5 — the only dot size animate-pulse is sanctioned for (§6) */}
          <div className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" aria-hidden="true" />
          <p className="fc-eyebrow text-primary uppercase" aria-hidden="true">
            Node: Alpha-7 Intake
          </p>
        </div>
        <h2 className="text-2xl lg:text-3xl font-heading font-bold fc-text-primary tracking-tight">
          Evidence Acquisition
        </h2>
      </div>

      {authError && (
        <div
          className="mb-6 p-4 rounded-xl border border-danger/20 bg-danger/5 text-sm fc-text-danger"
          role="alert"
        >
          <strong>Authentication Warning:</strong> {authError}. You can still select files, but starting the analysis may fail.
        </div>
      )}

      <motion.div
        ref={dropzoneRef}
        data-testid="upload-dropzone"
        role="button"
        tabIndex={0}
        aria-label="Evidence dropzone. Drag and drop or press Enter to browse files."
        aria-describedby="upload-file-help"
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
        // §6: no scale on interaction and no scan-beam loops — drag feedback is
        // expressed through border, tint, and an inner glow wash only.
        variants={{
          idle: {
            borderColor: "rgba(var(--color-primary-rgb),0.2)",
            backgroundColor: "rgba(var(--color-primary-rgb),0.02)",
          },
          active: {
            borderColor: "rgba(var(--color-primary-rgb),0.8)",
            backgroundColor: "rgba(var(--color-primary-rgb),0.08)",
          },
        }}
        transition={TRANSITION_FAST}
        className="fc-upload-zone w-full py-16 px-8 group flex flex-col items-center justify-center gap-4 relative overflow-hidden rounded-2xl border border-dashed fc-focus-ring cursor-pointer"
      >
        <AnimatePresence>
          {isDragging && (
            <motion.div
              initial={prefersReducedMotion ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={prefersReducedMotion ? {} : { opacity: 0 }}
              transition={{ duration: 0.16 }}
              className="absolute inset-0 z-10 pointer-events-none"
              style={{
                background:
                  "radial-gradient(ellipse at 50% 30%, rgba(var(--color-primary-rgb),0.14), transparent 70%)",
              }}
              aria-hidden="true"
            />
          )}
        </AnimatePresence>

        <CloudUpload
          className={`w-10 h-10 fc-transition relative z-20 ${
            isDragging ? "text-primary" : "fc-text-muted group-hover:text-foreground"
          }`}
          strokeWidth={1.2}
          aria-hidden="true"
        />

        <div className="flex flex-col items-center gap-2 pointer-events-none text-center relative z-20">
          {isSecuring ? (
            <span className="flex items-center gap-2 text-lg font-bold text-primary">
              <span
                className="w-4 h-4 rounded-full border-2 border-primary border-t-transparent animate-spin"
                aria-hidden="true"
              />
              Securing Evidence
            </span>
          ) : (
            <span className={`text-lg font-bold fc-transition ${
                isDragging ? "text-primary" : "fc-text-secondary group-hover:text-foreground"
              }`}
            >
              {isDragging ? "Drop to Upload" : "Select Evidence"}
            </span>
          )}
          <p id="upload-file-help" className="text-xs font-mono fc-text-muted opacity-70 uppercase tracking-wider">
            Images · Audio · Video · PDF &nbsp;·&nbsp; Max 50 MB
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
