/**
 * FileUploadSection Component
 * ===========================
 *
 * Displays the file upload form with drag-and-drop support,
 * file preview, and upload action buttons.
 */

import { useRef, useMemo, useEffect } from "react";
import {
  RotateCcw,
  ArrowRight,
  UploadCloud,
  FileAudio,
  File,
  ShieldAlert,
  ScanLine,
} from "lucide-react";
import { useSound } from "@/hooks/useSound";
import { clsx } from "clsx";

interface FileUploadSectionProps {
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
  const { playSound } = useSound();

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
      playSound("click");
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
      playSound("click");
      onFileDrop(droppedFile);
    }
  };

  return (
    <div
      key="upload"
      className="flex flex-col items-center justify-center min-h-[70vh] max-w-xl mx-auto"
    >
      {/* Title Section */}
      <div className="text-center mb-10">
        <div className="inline-flex items-center gap-2.5 px-4 py-2 rounded-full mb-6 relative overflow-hidden"
          style={{
            background: "rgba(34,211,238,0.05)",
            border: "1px solid rgba(34,211,238,0.12)",
          }}
        >
          <span className="relative flex h-2 w-2" aria-hidden="true">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-60" />
            <span className="relative inline-flex rounded-full h-full w-full bg-cyan-400" />
          </span>
          <span className="uppercase tracking-[0.35em] font-bold text-[9px]" style={{ color: "rgba(34,211,238,0.7)" }}>
            Evidence Intake Portal
          </span>
        </div>

        <h1 className="text-3xl md:text-4xl font-black mb-3 tracking-tight text-white leading-[1.1]">
          Initiate Investigation
        </h1>

        <p className="text-white/35 text-[11px] font-semibold uppercase tracking-[0.18em] max-w-sm mx-auto leading-relaxed">
          High-Precision Multi-Agent Forensic Auditing
        </p>
      </div>

      {/* File Preview or Upload Area */}
      {file ? (
        /* File selected – preview + action buttons */
        <div
          className="w-full rounded-2xl overflow-hidden relative"
          style={{
            background: "rgba(255,255,255,0.02)",
            backdropFilter: "blur(24px)",
            WebkitBackdropFilter: "blur(24px)",
            border: "1px solid rgba(255,255,255,0.06)",
            boxShadow: "0 8px 40px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.04)",
          }}
        >
          <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/25 to-transparent" />

          {/* Preview */}
          <div className="relative w-full" style={{ minHeight: "220px", background: "rgba(0,0,0,0.25)" }}>
            {file.type.startsWith("image/") && (
              /* eslint-disable-next-line @next/next/no-img-element -- Dynamic blob URL preview */
              <img
                src={filePreviewUrl ?? ""}
                alt={`Evidence preview: ${file.name}`}
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
                  <div
                    className="w-16 h-16 rounded-2xl flex items-center justify-center"
                    style={{
                      background: "rgba(52,211,153,0.08)",
                      border: "1px solid rgba(52,211,153,0.18)",
                      boxShadow: "0 0 24px rgba(16,185,129,0.12)",
                    }}
                  >
                    {file.type.startsWith("audio/") ? (
                      <FileAudio className="w-8 h-8 text-emerald-400" aria-hidden="true" />
                    ) : (
                      <File className="w-8 h-8 text-slate-400" aria-hidden="true" />
                    )}
                  </div>
                  {file.type.startsWith("audio/") && (
                    <div className="flex items-end gap-[3px] h-8" aria-hidden="true">
                      {[3, 7, 5, 9, 6, 4, 8, 5, 7, 3, 6, 8].map((_h, i) => (
                        <div
                          key={i}
                          className="w-[3px] rounded-full"
                          style={{
                            height: `${_h * 3.5}px`,
                            background: `rgba(34,211,238,${0.3 + _h * 0.05})`,
                          }}
                        />
                      ))}
                    </div>
                  )}
                </div>
              )}

            {/* File Info Overlay */}
            <div className="absolute bottom-0 inset-x-0 px-6 py-4"
              style={{ background: "linear-gradient(to top, rgba(0,0,0,0.85) 0%, transparent 100%)" }}
            >
              <p className="text-sm font-mono text-white truncate font-bold">{file.name}</p>
              <p className="text-[11px] text-white/40 mt-0.5 font-medium">
                {(file.size / 1024 / 1024).toFixed(2)} MB
              </p>
            </div>
          </div>

          {/* Action Buttons */}
          <div
            className="flex gap-3 p-4 relative"
            style={{ background: "rgba(0,0,0,0.15)", borderTop: "1px solid rgba(255,255,255,0.04)" }}
          >
            <button
              onClick={() => { playSound("click"); onClear(); }}
              disabled={isUploading}
              className="flex-1 py-3 rounded-xl text-[10px] font-bold uppercase tracking-[0.15em] flex items-center justify-center gap-2 transition-all duration-200 cursor-pointer disabled:cursor-not-allowed"
              style={{
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.08)",
                color: "rgba(255,255,255,0.5)",
              }}
            >
              <RotateCcw className="w-3.5 h-3.5 opacity-70" aria-hidden="true" />
              Reset
            </button>
            <button
              onClick={() => { playSound("upload"); onUpload(file); }}
              disabled={isUploading}
              className="flex-1 py-3 rounded-xl text-[10px] font-bold uppercase tracking-[0.15em] flex items-center justify-center gap-2 transition-all duration-200 cursor-pointer disabled:cursor-not-allowed relative overflow-hidden"
              style={{
                background: "linear-gradient(135deg, rgba(217,119,6,0.9) 0%, rgba(180,83,9,0.9) 100%)",
                color: "#fff",
                boxShadow: "0 0 24px rgba(217,119,6,0.25), inset 0 1px 0 rgba(255,255,255,0.15)",
              }}
            >
              {isUploading ? (
                <>
                  <UploadCloud className="w-4 h-4" aria-hidden="true" />
                  Sealing Evidence…
                </>
              ) : (
                <>
                  <ScanLine className="w-4 h-4" aria-hidden="true" />
                  Initiate Audit
                  <ArrowRight className="w-3.5 h-3.5 opacity-70" aria-hidden="true" />
                </>
              )}
            </button>
          </div>
        </div>
      ) : (
        /* No file selected – drag and drop area */
        <div
          role="button"
          tabIndex={0}
          aria-label="Upload evidence file. Click or drag and drop an image, video, or audio file here."
          className={clsx(
            "w-full group overflow-hidden rounded-2xl transition-all duration-500 relative cursor-pointer",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/50 focus-visible:ring-offset-4 focus-visible:ring-offset-background",
            isDragging ? "scale-[1.01]" : ""
          )}
          style={{
            background: isDragging ? "rgba(34,211,238,0.04)" : "rgba(255,255,255,0.015)",
            backdropFilter: "blur(20px)",
            WebkitBackdropFilter: "blur(20px)",
            border: isDragging
              ? "2px dashed rgba(34,211,238,0.5)"
              : "2px dashed rgba(255,255,255,0.07)",
            boxShadow: isDragging
              ? "0 0 40px rgba(34,211,238,0.08), inset 0 1px 0 rgba(255,255,255,0.03)"
              : "inset 0 1px 0 rgba(255,255,255,0.03), 0 4px 24px rgba(0,0,0,0.12)",
          }}
          onClick={() => { playSound("click"); fileInputRef.current?.click(); }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              fileInputRef.current?.click();
            }
          }}
          onDragEnter={handleDragEnter}
          onDragOver={(e) => { e.preventDefault(); if (!isDragging) onDragEnter(); }}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <div className="flex flex-col items-center justify-center py-14 px-8 gap-5 relative z-10">
            {/* Upload Icon */}
            <div
              className={clsx(
                "w-16 h-16 rounded-2xl flex items-center justify-center transition-all duration-300",
                isDragging ? "scale-110" : "group-hover:scale-105"
              )}
              style={{
                background: isDragging ? "rgba(34,211,238,0.1)" : "rgba(255,255,255,0.03)",
                border: isDragging
                  ? "1px solid rgba(34,211,238,0.3)"
                  : "1px solid rgba(255,255,255,0.06)",
                boxShadow: isDragging ? "0 0 30px rgba(34,211,238,0.15)" : "none",
              }}
            >
              <UploadCloud
                className={clsx(
                  "w-7 h-7 transition-all duration-300",
                  isDragging ? "text-cyan-400" : "text-white/20 group-hover:text-cyan-400/70"
                )}
                strokeWidth={1.5}
                aria-hidden="true"
              />
            </div>

            {/* Text */}
            <div className="text-center">
              <p
                className={clsx(
                  "text-base font-bold transition-colors duration-300 mb-1.5 tracking-tight",
                  isDragging ? "text-cyan-300" : "text-white/80 group-hover:text-white"
                )}
              >
                {isDragging ? "Release to submit" : "Drop evidence here"}
              </p>
              <p className="text-[11px] text-white/25 font-medium">
                or click to browse your files
              </p>
            </div>

            {/* Format Tags */}
            <div className="flex gap-2 flex-wrap justify-center mt-1">
              {["IMAGE", "VIDEO", "AUDIO"].map((t) => (
                <span
                  key={t}
                  className="px-3 py-1 rounded-lg text-[9px] font-bold text-white/25 tracking-[0.15em] uppercase transition-colors duration-300 group-hover:text-white/40"
                  style={{
                    background: "rgba(255,255,255,0.03)",
                    border: "1px solid rgba(255,255,255,0.05)",
                  }}
                >
                  {t}
                </span>
              ))}
            </div>

            {/* Size limit hint */}
            <p className="text-[10px] text-white/15 font-mono tracking-wide mt-1">
              Max file size: 50 MB
            </p>
          </div>
        </div>
      )}

      {/* Validation Error */}
      {validationError && (
        <div
          role="alert"
          aria-live="assertive"
          className="mt-6 p-4 rounded-xl max-w-md w-full flex items-start gap-3"
          style={{
            background: "rgba(239,68,68,0.06)",
            border: "1px solid rgba(239,68,68,0.2)",
            boxShadow: "0 8px 30px rgba(239,68,68,0.1)",
          }}
        >
          <ShieldAlert className="w-5 h-5 text-red-400 shrink-0 mt-0.5" aria-hidden="true" />
          <span className="text-sm text-red-200 font-medium leading-relaxed">{validationError}</span>
        </div>
      )}

      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        onChange={handleFileChange}
        className="sr-only"
        accept="image/*,video/*,audio/*"
        aria-label="Upload evidence file"
      />
    </div>
  );
}
