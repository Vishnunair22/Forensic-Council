"use client";

import { useEffect, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { motion } from "framer-motion";
import { X, Upload } from "lucide-react";

export interface UploadModalProps {
  onClose: () => void;
  onFileSelected: (file: File) => void;
}

export function UploadModal({ onClose, onFileSelected }: UploadModalProps) {
  const [mounted, setMounted] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

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

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      onFileSelected(e.dataTransfer.files[0]);
    }
  }, [onFileSelected]);

  if (!mounted) return null;

  return createPortal(
    <motion.div
      initial={{ opacity: 0, backdropFilter: "blur(0px)" }}
      animate={{ opacity: 1, backdropFilter: "blur(12px)" }}
      exit={{ opacity: 0, backdropFilter: "blur(0px)", transition: { delay: 0.3 } }}
      onClick={onClose}
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 p-4"
    >
      <div 
        className="relative w-full max-w-xl" 
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Content */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.95 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
          className="relative z-30 bg-white/[0.04] backdrop-blur-xl border border-white/10 rounded-3xl p-10 shadow-[0_0_80px_rgba(0,0,0,0.9)] overflow-hidden"
        >
          <button 
            onClick={onClose}
            className="absolute top-6 right-6 text-white/40 hover:text-white transition-colors z-50"
          >
            <X className="w-5 h-5" />
          </button>

          <div className="flex flex-col items-center text-center gap-8">
            {/* The fixed, robust dropzone */}
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              className={`w-full border border-dashed rounded-3xl px-8 py-16 transition-all duration-300 cursor-pointer group flex flex-col items-center justify-center gap-6 relative overflow-hidden z-50 ${
                isDragging 
                  ? "border-primary bg-primary/[0.05]" 
                  : "border-white/[0.15] hover:border-primary/50 hover:bg-primary/[0.03] bg-white/[0.02]"
              }`}
            >
              <div className="relative z-10 flex h-20 w-20 items-center justify-center rounded-2xl bg-white/[0.05] text-white/50 transition-all duration-300 group-hover:bg-primary/10 group-hover:text-primary">
                <Upload className="h-10 w-10" strokeWidth={1.5} />
              </div>

              <div className="flex flex-col items-center gap-2 z-10 pointer-events-none">
                <span className={`text-xl font-bold transition-colors ${isDragging ? "text-primary" : "text-white/90 group-hover:text-primary"}`}>
                  {isDragging ? "Release Payload" : "Upload Evidence"}
                </span>
                <p className="text-sm font-medium text-white/40 max-w-xs leading-relaxed">
                  Upload image, audio, video for forensic analysis.
                </p>
              </div>
              
              <input
                type="file" 
                aria-label="Upload evidence file"
                className="absolute inset-0 z-20 h-full w-full cursor-pointer opacity-0"
                accept="image/*,video/*,audio/*"
                onChange={(e) => {
                  if (e.target.files?.[0]) onFileSelected(e.target.files[0]);
                }}
              />
            </div>
          </div>
        </motion.div>
      </div>
    </motion.div>,
    document.body
  );
}
