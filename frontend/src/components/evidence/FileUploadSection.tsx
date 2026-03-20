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
  FileAudio,
  File,
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
        <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full
          bg-white/[0.05] border border-white/[0.10]
          text-xs font-mono text-cyan-400 backdrop-blur-md mb-6
          shadow-[0_0_20px_rgba(0,212,255,0.06)]">
          <span className="relative flex h-2 w-2" aria-hidden="true">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-70" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500" />
          </span>
          <span className="uppercase tracking-widest">Evidence Intake Terminal</span>
        </div>
        <h1 className="text-4xl md:text-5xl font-extrabold mb-4 tracking-tight
          bg-gradient-to-b from-white via-white to-slate-400 bg-clip-text text-transparent leading-[1.05] pb-1">
          Initiate Investigation.
        </h1>
        <p className="text-slate-400 text-base font-normal max-w-md mx-auto leading-relaxed">
          Deploy the{" "}
          <span className="text-emerald-400 font-semibold">
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
                  <div className="w-16 h-16 rounded-2xl bg-emerald-500/10 border border-emerald-500/22 flex items-center justify-center shadow-[0_0_22px_rgba(16,185,129,0.16)]">
                    {file.type.startsWith("audio/") ? (
                      <FileAudio className="w-8 h-8 text-emerald-400" aria-hidden="true" />
                    ) : (
                      <File className="w-8 h-8 text-slate-400" aria-hidden="true" />
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
              className="btn btn-ghost flex-1 py-3.5 rounded-xl"
            >
              <RotateCcw className="w-4 h-4" aria-hidden="true" />
              Clear
            </button>
            <button
              onClick={() => onUpload(file)}
              disabled={isUploading}
              className="btn btn-primary flex-1 py-3.5 rounded-xl font-bold"
            >
              {isUploading ? (
                <>
                  <motion.div animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity }}>
                    <UploadCloud className="w-4 h-4" aria-hidden="true" />
                  </motion.div>
                  Uploading…
                </>
              ) : (
                <>
                  <ArrowRight className="w-4 h-4" aria-hidden="true" />
                  Analyze Evidence
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
          role="button"
          tabIndex={0}
          aria-label="File drop zone — click or press Enter to browse"
          onClick={() => fileInputRef.current?.click()}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInputRef.current?.click(); } }}
          className={`w-full glass-panel rounded-[2rem] overflow-hidden border-2 border-dashed
            transition-all duration-300 relative cursor-pointer
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 focus-visible:ring-offset-2 focus-visible:ring-offset-transparent
            ${isDragging
              ? "border-emerald-500/75 shadow-[inset_0_0_50px_rgba(16,185,129,0.07)]"
              : "border-white/[0.09] hover:border-emerald-500/42 hover:shadow-[inset_0_0_35px_rgba(16,185,129,0.04)]"
            }`}
        >
          {/* Drag glow */}
          <motion.div animate={{ opacity: isDragging ? 1 : 0 }} transition={{ duration: 0.2 }}
            className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(16,185,129,0.08),transparent_68%)] pointer-events-none" />

          <div className="flex flex-col items-center justify-center py-16 px-8 gap-4">
            <motion.div
              animate={{ scale: isDragging ? 1.12 : 1 }}
              transition={{ type: "spring", stiffness: 300, damping: 20 }}
              className={`w-[72px] h-[72px] rounded-2xl flex items-center justify-center transition-all duration-200
                bg-gradient-to-br from-emerald-500/18 to-emerald-600/8
                border shadow-[0_0_24px_rgba(16,185,129,0.16)]
                ${isDragging ? "border-emerald-400/55 shadow-[0_0_36px_rgba(16,185,129,0.28)]" : "border-emerald-500/25"}`}
            >
              <UploadCloud className={`w-8 h-8 transition-colors duration-200 ${isDragging ? "text-emerald-200" : "text-emerald-400"}`} aria-hidden="true" />
            </motion.div>
            <div className="text-center">
              <p className="text-base font-semibold text-white mb-1 tracking-wide">
                {isDragging ? "Drop your evidence here" : "Drag evidence file here"}
              </p>
              <p className="text-sm text-slate-400">
                or click to select from your system
              </p>
            </div>
            <div className="flex gap-2 flex-wrap justify-center mt-1">
              {["IMAGE", "VIDEO", "AUDIO"].map(t => (
                <span key={t} className="px-2.5 py-0.5 bg-white/[0.04] border border-white/[0.08]
                  rounded-full text-[10px] font-mono text-slate-500 tracking-widest">
                  {t}
                </span>
              ))}
            </div>
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
