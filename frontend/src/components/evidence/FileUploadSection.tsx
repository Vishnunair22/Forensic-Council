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
      
      
      
      className="flex flex-col items-center justify-center min-h-[50vh] max-w-xl mx-auto"
    >
      {/* Title Section */}
      <div className="text-center mb-7">
        <div
          
          
          
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full mb-5 shadow-sm relative overflow-hidden group"
            style={{ background: "rgba(34,211,238,0.06)", border: "1px solid rgba(34,211,238,0.14)" }}>
          <span className="relative flex h-1.5 w-1.5" aria-hidden="true">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-50" />
            <span className="relative inline-flex rounded-full h-full w-full bg-cyan-400" />
          </span>
          <span className="uppercase tracking-[0.4em] font-bold font-sans text-[9px]" style={{ color: "rgba(34,211,238,0.6)" }}>Evidence Intake Portal</span>
        </div>

        <h1
          
          
          
          className="text-2xl md:text-3xl font-bold mb-2.5 tracking-tight font-heading
            text-foreground leading-[1.1]">
          Initiate Investigation
        </h1>

        <p
          
          
          
          className="text-white/40 text-[10px] font-bold uppercase tracking-[0.2em] max-w-sm mx-auto leading-relaxed italic">
          High-Precision Multi-Agent Forensic Auditing
        </p>
      </div>

      {/* File Preview or Upload Area */}
      {file ? (
        /* File selected – preview + action buttons */
        <div
          
          
          className="w-full glass-ethereal rounded-[2rem] overflow-hidden relative"
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
                  <div className="w-16 h-16 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center shadow-[0_0_22px_rgba(16,185,129,0.16)]">
                    {file.type.startsWith("audio/") ? (
                      <FileAudio className="w-8 h-8 text-emerald-400" aria-hidden="true" />
                    ) : (
                      <File className="w-8 h-8 text-slate-400" aria-hidden="true" />
                    )}
                  </div>
                  {file.type.startsWith("audio/") && (
                    <div className="flex items-end gap-1 h-8">
                      {[3, 7, 5, 9, 6, 4, 8, 5, 7, 3, 6, 8].map((h, i) => (
                          <div
                            key={i}
                            
                            
                            className="w-1 bg-cyan-400/60 rounded-full"
                          />
                      ))}
                    </div>
                  )}
                </div>
              )}

            {/* File Info */}
            <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/80 to-transparent px-6 py-4">
              <p className="text-sm font-mono text-white truncate font-bold">
                {file.name}
              </p>
              <p className="text-[12px] text-slate-300 mt-0.5 font-medium">
                {(file.size / 1024 / 1024).toFixed(2)} MB
              </p>
            </div>
          </div>

          <div className="flex gap-3 p-4 bg-black/40 border-t border-white/[0.08] relative">
            <button
              onClick={() => { playSound("click"); onClear(); }}
              disabled={isUploading}
              className="btn-premium-glass flex-1 py-2 rounded-lg text-[10px] font-bold uppercase tracking-[0.15em]"
            >
              <RotateCcw className="w-3.5 h-3.5 opacity-70" aria-hidden="true" />
              Reset
            </button>
            <button
              onClick={() => { playSound("upload"); onUpload(file); }}
              disabled={isUploading}
              className="btn-premium-amber flex-1 py-3 justify-center relative overflow-hidden rounded shadow-[0_0_20px_rgba(217,119,6,0.2)]"
            >
              {isUploading ? (
                <>
                  <div  >
                    <UploadCloud className="w-4 h-4" aria-hidden="true" />
                  </div>
                  SEALING EVIDENCE…
                </>
              ) : (
                <>
                  <ArrowRight className="w-4 h-4" aria-hidden="true" />
                  INITIATE AUDIT
                </>
              )}
            </button>
          </div>
        </div>
      ) : (
        /* No file selected – drag and drop area */
        <div
          className={clsx(
            "surface-panel-high w-full group overflow-hidden border-2 border-dashed rounded transition-all duration-700 relative cursor-pointer",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/50 focus-visible:ring-offset-8 focus-visible:ring-offset-background",
            isDragging
              ? "border-cyan-400 bg-cyan-500/5 scale-[1.01]"
              : "border-white/5 hover:border-cyan-500/35"
          )}
          onClick={() => { playSound("click"); fileInputRef.current?.click(); }}
          onDragEnter={handleDragEnter}
          onDragOver={(e) => { e.preventDefault(); if (!isDragging) onDragEnter(); }}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <div className="flex flex-col items-center justify-center py-10 px-6 gap-4 relative z-10">
            <div
              
              
              className={`w-12 h-12 rounded-xl flex items-center justify-center transition-all duration-300
                border
                ${isDragging
                  ? "border-cyan-400/60 shadow-lg shadow-cyan-500/10"
                  : "border-white/5 group-hover:border-cyan-500/30 group-hover:bg-cyan-500/5"}`}
              style={{ background: "rgba(255,255,255,0.04)" }}
            >
              <UploadCloud className={`w-5 h-5 transition-all duration-300 ${isDragging ? "text-cyan-400" : "text-white/20 group-hover:text-cyan-400"}`} strokeWidth={1} aria-hidden="true" />
            </div>

            <div className="text-center">
              <p className={`text-sm font-black transition-colors duration-300 mb-1 tracking-tight font-heading uppercase ${isDragging ? "text-cyan-400" : "text-white group-hover:text-cyan-300"}`}>
                {isDragging ? "Seize specimen" : "Deposit evidence specimen"}
              </p>
              <p className="text-[10px] text-white/20 font-mono uppercase tracking-[0.2em] font-bold">
                Secure Intake Portal — Click to Browse
              </p>
            </div>

            <div className="flex gap-2 flex-wrap justify-center">
              {["IMAGE", "VIDEO", "AUDIO"].map(t => (
                <span key={t} className="px-2.5 py-0.5 bg-surface-mid border border-border-subtle
                  rounded text-[9px] font-mono text-foreground/30 tracking-widest uppercase transition-colors group-hover:border-border-bold group-hover:text-foreground/60 font-bold">
                  {t}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Validation Error */}
      {validationError && (
        <div
          
          
          className="mt-6 p-4 rounded-xl glass-ethereal border border-red-500/40 text-red-200 text-sm max-w-md w-full flex items-start gap-3 shadow-[0_8px_30px_rgba(239,68,68,0.2)]"
        >
          <ShieldAlert className="w-5 h-5 text-red-500 shrink-0" />
          <span className="font-medium leading-relaxed">{validationError}</span>
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
