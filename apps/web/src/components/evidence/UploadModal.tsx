"use client";

import { useEffect, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { motion } from "framer-motion";
import { X } from "lucide-react";
import { ALLOWED_MIME_TYPES, MAX_UPLOAD_SIZE_BYTES } from "@/lib/constants";

function EnvelopeOpen({ isDragging, isOpen }: { isDragging: boolean; isOpen: boolean }) {
  return (
    <div className="relative flex h-24 w-24 items-center justify-center">
      <motion.div
        animate={{ rotate: 360 }}
        transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
        className="absolute inset-0 rounded-full border border-primary/20 border-dashed"
      />
      <div className="absolute inset-2 rounded-full border border-primary/10" />
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
          <motion.path
            d="M2 12 L2 42 Q2 46 6 46 L58 46 Q62 46 62 42 L62 12 Q62 8 58 8 L6 8 Q2 8 2 12Z"
            fill="url(#envBody)"
            stroke="#475569"
            strokeWidth="1"
          />
          <motion.path
            d="M2 12 L32 28 L62 12"
            fill="none"
            stroke="#475569"
            strokeWidth="1"
          />
          <motion.g>
            <motion.path
              d="M2 8 L32 26 L62 8"
              fill="url(#envFlap)"
              stroke="#64748b"
              strokeWidth="0.5"
              initial={{ rotateX: 180, opacity: 0.9 }}
              animate={{ rotateX: isOpen ? 0 : 180, opacity: 1 }}
              transition={{ duration: 0.38, ease: [0.34, 1.56, 0.64, 1] }}
              style={{ transformOrigin: "32px 26px" }}
            />
            <motion.rect
              x="10"
              y="22"
              width="44"
              height="18"
              rx="1"
              fill="#f8fafc"
              initial={{ y: 20, opacity: 0 }}
              animate={{ y: (isDragging || isOpen) ? 0 : 8, opacity: (isDragging || isOpen) ? 1 : 0.6 }}
              transition={{ duration: 0.35, ease: "easeOut" }}
            />
            <motion.path
              d="M16 28 L28 36"
              stroke="#94a3b8"
              strokeWidth="1.5"
              initial={{ opacity: 0 }}
              animate={{ opacity: (isDragging || isOpen) ? 1 : 0.4 }}
              transition={{ delay: 0.15, duration: 0.2 }}
            />
            <motion.path
              d="M36 28 L48 36"
              stroke="#94a3b8"
              strokeWidth="1.5"
              initial={{ opacity: 0 }}
              animate={{ opacity: (isDragging || isOpen) ? 1 : 0.4 }}
              transition={{ delay: 0.2, duration: 0.2 }}
            />
          </motion.g>
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
  const [hasOpened, setHasOpened] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setMounted(true);
    const t = setTimeout(() => setHasOpened(true), 50);   // trigger open
    const originalBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      clearTimeout(t);
      if (originalBodyOverflow !== "hidden") {
        document.body.style.overflow = originalBodyOverflow;
      } else {
        document.body.style.overflow = "";
      }
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
      exit={{ opacity: 0, rotateY: 90, transition: { duration: 0.3 } }}
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
              <EnvelopeOpen isDragging={isDragging} isOpen={hasOpened} />

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
                onClick={(e) => { (e.target as HTMLInputElement).value = ""; }}
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
