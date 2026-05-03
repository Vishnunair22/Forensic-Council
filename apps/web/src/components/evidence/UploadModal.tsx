"use client";

import { useEffect, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { motion } from "framer-motion";
import { X, Upload } from "lucide-react";
import { ALLOWED_MIME_TYPES, MAX_UPLOAD_SIZE_BYTES } from "@/lib/constants";

export interface UploadModalProps {
  onClose: () => void;
  onFileSelected: (file: File) => void;
}

export function UploadModal({ onClose, onFileSelected }: UploadModalProps) {
  const [mounted, setMounted] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setMounted(true);
    const originalBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = originalBodyOverflow || "unset";
    };
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
    if (file.size > MAX_UPLOAD_SIZE_BYTES) {
      setError("File must be 50MB or smaller.");
      return;
    }
    if (!ALLOWED_MIME_TYPES.has(file.type)) {
      setError(`File type "${file.type || "unknown"}" is not supported.`);
      return;
    }
    setError(null);
    onFileSelected(file);
  }, [onFileSelected]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      selectFile(e.dataTransfer.files[0]);
    }
  }, [selectFile]);

  if (!mounted) return null;

  return createPortal(
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: 0.12, ease: "easeOut" } }}
      transition={{ duration: 0.14, ease: "easeOut" }}
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-slate-950/80 backdrop-blur-xl p-4"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className="relative w-full max-w-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.98, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.985, y: 6 }}
          transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
          className="horizon-card p-1 relative overflow-hidden"
        >
          {/* Beveled Interior */}
          <div className="bg-[#020617] rounded-[inherit] p-10 flex flex-col items-center text-center">

            <button
              onClick={onClose}
              className="absolute top-6 right-6 text-white/20 hover:text-primary transition-colors"
              aria-label="Close upload dialog"
            >
              <X className="w-5 h-5" />
            </button>

            <h2 className="text-2xl font-heading font-bold text-white mb-8">Upload Evidence</h2>

            <div
              data-testid="upload-dropzone"
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              className={`w-full border-2 border-dashed rounded-2xl p-16 transition-all duration-500 cursor-pointer group flex flex-col items-center justify-center gap-6 relative overflow-hidden ${
                isDragging
                  ? "border-primary bg-primary/5 shadow-[0_0_40px_rgba(0,255,255,0.1)]"
                  : "border-white/5 hover:border-primary/40 hover:bg-white/[0.02]"
              }`}
            >
              {/* Aperture Animation around icon */}
              <div className="relative flex h-24 w-24 items-center justify-center">
                <motion.div
                  animate={{ rotate: 360 }}
                  transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
                  className="absolute inset-0 rounded-full border border-primary/20 border-dashed"
                />
                <div className="absolute inset-2 rounded-full border border-primary/10" />
                <Upload className={`h-10 w-10 transition-colors duration-300 ${isDragging ? "text-primary" : "text-white/30 group-hover:text-primary"}`} strokeWidth={1.5} />
              </div>

              <div className="flex flex-col items-center gap-2 pointer-events-none">
                <span className={`text-xl font-heading font-bold tracking-tight transition-colors ${isDragging ? "text-primary" : "text-white/80 group-hover:text-primary"}`}>
                  {isDragging ? "Release Payload" : "Drop Evidence File"}
                </span>
                <p className="text-sm font-medium text-white/30 max-w-[240px] leading-relaxed">
                  Select a forensic file for multi-agent neural verification.
                </p>
              </div>

              {/* HUD Corner Marker */}
              <div className="absolute bottom-4 right-4 text-[9px] font-mono text-primary/20 tracking-widest">
                WAITING_FOR_DATA
              </div>

              <input
                type="file"
                aria-label="Upload evidence file"
                className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                accept={Array.from(ALLOWED_MIME_TYPES).join(",")}
                onChange={(e) => {
                  if (e.target.files?.[0]) selectFile(e.target.files[0]);
                }}
              />
            </div>
            {error && (
              <p className="mt-4 text-sm font-semibold text-red-400" role="alert">
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
