/**
 * FileUploadSection Component
 * ===========================
 * 
 * Displays the file upload form with drag-and-drop support,
 * file preview, and upload action buttons.
 */

import { useRef, useMemo, useEffect } from "react";
import { motion } from "framer-motion";
import {
  RotateCcw,
  ArrowRight,
  UploadCloud,
} from "lucide-react";

interface FileUploadSectionProps {
  key?: React.Key;
  file: File | null;
  isDragging: boolean;
  isUploading: boolean;
  validationError: string | null;
  onFileSelect: (file: File) => void;
  onFileDrop: (file: File) => void;
  onDragEnter: () => void;
  onDragLeave: () => void;
  onUpload: (file: File) => void;
  onClear: () => void;
}

export function FileUploadSection({
  file,
  isDragging,
  isUploading,
  validationError,
  onFileSelect,
  onFileDrop,
  onDragEnter,
  onDragLeave,
  onUpload,
  onClear,
}: FileUploadSectionProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Memoize file preview URL to avoid memory leaks
  const filePreviewUrl = useMemo(() => {
    if (!file) return null;
    if (file.type.startsWith("image/") || file.type.startsWith("video/")) {
      return URL.createObjectURL(file);
    }
    return null;
  }, [file]);

  // Cleanup blob URL on unmount or when file changes
  useEffect(() => {
    return () => {
      if (filePreviewUrl) {
        URL.revokeObjectURL(filePreviewUrl);
      }
    };
  }, [filePreviewUrl]);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = event.target.files?.[0];
    if (selectedFile) {
      onFileSelect(selectedFile);
    }
  };

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    onDragEnter();
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    onDragLeave();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    onDragLeave();
    const droppedFile = e.dataTransfer.files?.[0];
    if (droppedFile) {
      onFileDrop(droppedFile);
    }
  };

  return (
    <motion.div
      key="upload"
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, y: -20 }}
      className="flex flex-col items-center justify-center min-h-[60vh] max-w-2xl mx-auto"
    >
      {/* Title Section */}
      <div className="text-center mb-10">
        <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/5 border border-white/10 text-sm text-cyan-400 backdrop-blur-md mb-6">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500" />
          </span>
          Evidence Intake Terminal
        </div>
        <h1 className="text-4xl md:text-5xl font-black mb-4 tracking-tight">
          Initiate Investigation.
        </h1>
        <p className="text-slate-400 text-lg font-light max-w-md mx-auto">
          Deploy the{" "}
          <span className="text-emerald-400 font-medium">
            Council Autonomous Parsing System
          </span>{" "}
          on your digital artifact.
        </p>
      </div>

      {/* File Preview or Upload Area */}
      {file ? (
        /* File selected – preview + action buttons */
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="w-full glass-panel rounded-[2rem] overflow-hidden relative"
        >
          <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/30 to-transparent" />

          {/* Preview */}
          <div className="relative w-full bg-black/40" style={{ minHeight: "200px" }}>
            {file.type.startsWith("image/") && (
              /* eslint-disable-next-line @next/next/no-img-element -- Dynamic blob URL preview */
              <img
                src={filePreviewUrl ?? ""}
                alt="Evidence"
                className="w-full max-h-72 object-contain"
              />
            )}
            {file.type.startsWith("video/") && (
              <video
                src={filePreviewUrl ?? ""}
                className="w-full max-h-72 object-contain"
                muted
                autoPlay
                loop
                playsInline
              />
            )}
            {!file.type.startsWith("image/") &&
              !file.type.startsWith("video/") && (
                <div className="flex flex-col items-center justify-center h-52 gap-4">
                  <div className="w-16 h-16 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center shadow-[0_0_20px_rgba(16,185,129,0.15)]">
                    {file.type.startsWith("audio/") ? (
                      <span className="text-3xl">🎵</span>
                    ) : (
                      <span className="text-3xl">📄</span>
                    )}
                  </div>
                  {file.type.startsWith("audio/") && (
                    <div className="flex items-end gap-1 h-8">
                      {[3, 7, 5, 9, 6, 4, 8, 5, 7, 3, 6, 8].map((h, i) => (
                        <motion.div
                          key={i}
                          animate={{
                            height: `${h}px`,
                          }}
                          transition={{
                            duration: 0.4,
                            repeat: Infinity,
                            repeatType: "reverse",
                            delay: i * 0.05,
                          }}
                          className="w-1 bg-emerald-500/60 rounded-full"
                        />
                      ))}
                    </div>
                  )}
                </div>
              )}

            {/* File Info */}
            <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/80 to-transparent px-6 py-4">
              <p className="text-sm font-mono text-white truncate font-semibold">
                {file.name}
              </p>
              <p className="text-[11px] text-slate-400 mt-0.5">
                {(file.size / 1024 / 1024).toFixed(2)} MB
              </p>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex gap-3 p-6">
            <button
              onClick={onClear}
              disabled={isUploading}
              className="flex-1 flex items-center justify-center gap-2 px-5 py-3.5 rounded-xl bg-slate-900/40 border border-slate-700/30 text-slate-300 hover:bg-slate-900/60 disabled:opacity-50 transition-all font-medium"
            >
              <RotateCcw className="w-4 h-4 text-slate-400" />
              Clear
            </button>
            <button
              onClick={() => onUpload(file)}
              disabled={isUploading}
              className="flex-1 flex items-center justify-center gap-2 px-5 py-3.5 rounded-xl bg-emerald-600/30 border border-emerald-500/50 text-emerald-300 hover:bg-emerald-600/50 disabled:opacity-50 transition-all font-medium"
            >
              {isUploading ? (
                <>
                  <motion.div animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity }}>
                    <UploadCloud className="w-4 h-4" />
                  </motion.div>
                  Uploading...
                </>
              ) : (
                <>
                  <ArrowRight className="w-4 h-4" />
                  Analyze
                </>
              )}
            </button>
          </div>
        </motion.div>
      ) : (
        /* No file selected – drag and drop area */
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          onDragEnter={handleDragEnter}
          onDragOver={(e) => { e.preventDefault(); if (!isDragging) onDragEnter(); }}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`w-full glass-panel rounded-[2rem] overflow-hidden border-2 border-dashed transition-all duration-300 ${isDragging
              ? "border-emerald-500/70"
              : "border-white/[0.10]"
            } relative cursor-pointer`}
        >
          <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/30 to-transparent" />

          <div
            className="flex flex-col items-center justify-center py-16 gap-4"
            onClick={() => fileInputRef.current?.click()}
          >
            <motion.div
              animate={{
                scale: isDragging ? 1.1 : 1,
              }}
              className="w-16 h-16 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center shadow-[0_0_20px_rgba(16,185,129,0.15)]"
            >
              <UploadCloud className="w-8 h-8 text-emerald-400" />
            </motion.div>
            <div className="text-center">
              <p className="text-lg font-semibold text-white mb-1">
                {isDragging
                  ? "Drop your evidence here"
                  : "Drag evidence file here"}
              </p>
              <p className="text-sm text-slate-400">
                or click to select from your system
              </p>
            </div>
            <p className="text-xs text-slate-500 mt-2">
              Supported: Images, Video, Audio, Documents
            </p>
          </div>
        </motion.div>
      )}

      {/* Validation Error */}
      {validationError && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-6 p-4 rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 text-sm max-w-md"
        >
          <span className="font-medium">{validationError}</span>
        </motion.div>
      )}

      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        onChange={handleFileChange}
        className="hidden"
        accept="image/*,video/*,audio/*,.pdf,.doc,.docx"
        aria-label="Upload evidence file"
      />
    </motion.div>
  );
}
