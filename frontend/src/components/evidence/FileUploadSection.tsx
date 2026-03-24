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
  ShieldAlert,
} from "lucide-react";
import { useSound } from "@/hooks/useSound";
import { clsx } from "clsx";
import { CyberNoirPanel } from "@/components/ui/CyberNoirPanel";

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
    <motion.div
      key="upload"
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, y: -20 }}
      className="flex flex-col items-center justify-center min-h-[60vh] max-w-2xl mx-auto"
    >
      {/* Title Section */}
      <div className="text-center mb-12">
        <motion.div 
          initial={{ y: -10, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="inline-flex items-center gap-2.5 px-5 py-2.5 rounded-full
            bg-white/[0.02] border border-white/[0.08]
            text-xs font-mono text-cyan-400 backdrop-blur-xl mb-8
            shadow-[0_0_30px_rgba(0,212,255,0.08)] relative overflow-hidden group">
          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-400/10 to-transparent translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-1000" />
          <span className="relative flex h-2 w-2 shadow-[0_0_10px_#00d4ff]" aria-hidden="true">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-80" />
            <span className="relative inline-flex rounded-full h-full w-full bg-cyan-400" />
          </span>
          <span className="uppercase tracking-[0.2em] font-bold text-[12px] text-cyan-200">Evidence Intake Terminal</span>
        </motion.div>
        
        <motion.h1 
          initial={{ y: 10, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.1, duration: 0.8, ease: "easeOut" }}
          className="text-4xl md:text-5xl font-black mb-5 tracking-tight font-heading
            bg-gradient-to-br from-white via-white to-slate-500 bg-clip-text text-transparent leading-[1.1] pb-2">
          Initiate Investigation.
        </motion.h1>
        
        <motion.p 
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2, duration: 0.8 }}
          className="text-slate-400 text-sm md:text-base font-medium max-w-lg mx-auto leading-relaxed">
          Deploy the <span className="text-cyan-400 font-bold tracking-wide">Council Autonomous Parsing System</span> on your digital artifact.
        </motion.p>
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
              <p className="text-sm font-mono text-white truncate font-bold">
                {file.name}
              </p>
              <p className="text-[12px] text-slate-300 mt-0.5 font-medium">
                {(file.size / 1024 / 1024).toFixed(2)} MB
              </p>
            </div>
          </div>

          <div className="flex gap-4 p-8 bg-black/40 border-t border-white/[0.08] relative">
            <button
              onClick={() => { playSound("click"); onClear(); }}
              disabled={isUploading}
              className="btn btn-ghost flex-1 py-4 rounded-xl text-xs font-bold uppercase tracking-widest"
            >
              <RotateCcw className="w-4 h-4 opacity-70" aria-hidden="true" />
              Reset Terminal
            </button>
            <button
              onClick={() => { playSound("upload"); onUpload(file); }}
              disabled={isUploading}
              className="btn btn-cyan flex-1 py-4 rounded-xl text-xs font-bold uppercase tracking-widest relative overflow-hidden"
            >
              {isUploading ? (
                <>
                  <motion.div animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity, ease: "linear" }}>
                    <UploadCloud className="w-4 h-4" aria-hidden="true" />
                  </motion.div>
                  Initiating Scan…
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
        <CyberNoirPanel
          glow={isDragging ? "cyan" : "none"}
          intensity={isDragging ? "high" : "medium"}
          className={clsx(
            "w-full group overflow-hidden border-2 border-dashed rounded-[3rem] transition-all duration-700 relative cursor-pointer",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/50 focus-visible:ring-offset-8 focus-visible:ring-offset-black",
            isDragging
              ? "border-cyan-400 shadow-[0_0_80px_rgba(0,212,255,0.15)] scale-[1.03]"
              : "border-white/10 hover:border-cyan-500/40"
          )}
          onClick={() => { playSound("click"); fileInputRef.current?.click(); }}
          onDragEnter={handleDragEnter}
          onDragOver={(e) => { e.preventDefault(); if (!isDragging) onDragEnter(); }}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          {/* Subtle noise texture */}
          <div className="absolute inset-0 opacity-[0.03] bg-[url('data:image/svg+xml,%3Csvg viewBox=%220 0 200 200%22 xmlns=%22http://www.w3.org/2000/svg%22%3E%3Cfilter id=%22noiseFilter%22%3E%3CfeTurbulence type=%22fractalNoise%22 baseFrequency=%220.85%22 numOctaves=%223%22 stitchTiles=%22stitch%22/%3E%3C/filter%3E%3Crect width=%22100%25%22 height=%22100%25%22 filter=%22url(%23noiseFilter)%22/%3E%3C/svg%3E')] mix-blend-overlay pointer-events-none" />
          
          {/* Scanning laser effect (static visual placeholder, CSS handles animation) */}
          <div className="absolute inset-0 pointer-events-none">
             <div className="absolute top-0 left-0 right-0 h-[2px] bg-cyan-400/50 shadow-[0_0_15px_rgba(0,212,255,1)] animate-[scan-v_4s_linear_infinite]" />
          </div>

          <div className="flex flex-col items-center justify-center py-20 px-8 gap-6 relative z-10">
            <motion.div
              animate={{ 
                scale: isDragging ? 1.15 : 1,
                y: isDragging ? -5 : 0 
              }}
              transition={{ type: "spring", stiffness: 400, damping: 25 }}
              className={`w-[88px] h-[88px] rounded-2xl flex items-center justify-center transition-all duration-300
                bg-gradient-to-br border 
                ${isDragging 
                  ? "from-cyan-600/20 to-violet-700/20 border-cyan-400/60 shadow-[0_0_40px_rgba(0,212,255,0.3)]" 
                  : "from-white/[0.03] to-white/[0.01] border-white/10 group-hover:border-cyan-500/30 group-hover:shadow-[0_0_30px_rgba(0,212,255,0.15)] group-hover:from-cyan-600/10 group-hover:to-transparent"}`}
            >
              <UploadCloud className={`w-10 h-10 transition-all duration-300 ${isDragging ? "text-cyan-300 drop-shadow-[0_0_10px_rgba(0,212,255,0.8)]" : "text-slate-400 group-hover:text-cyan-400"}`} strokeWidth={1.5} aria-hidden="true" />
            </motion.div>
            
            <div className="text-center">
              <p className={`text-lg font-bold transition-colors duration-300 mb-2 tracking-wide font-heading ${isDragging ? "text-cyan-300" : "text-white group-hover:text-cyan-50"}`}>
                {isDragging ? "Drop Evidence Specimen" : "Drag Evidence Specimen"}
              </p>
              <p className="text-xs text-slate-400 font-mono uppercase tracking-widest font-bold">
                Secure Intake Portal — Click to Browse
              </p>
            </div>
            
            <div className="flex gap-2.5 flex-wrap justify-center mt-2">
              {["IMAGE", "VIDEO", "AUDIO", "DOCUMENT"].map(t => (
                <span key={t} className="px-3 py-1 bg-black/40 border border-white/[0.08]
                  rounded-md text-[10px] font-mono text-slate-400 tracking-widest uppercase transition-colors group-hover:border-white/20 group-hover:text-white font-bold">
                  {t}
                </span>
              ))}
            </div>
          </div>
        </CyberNoirPanel>
      )}

      {/* Validation Error */}
      {validationError && (
        <motion.div
          initial={{ opacity: 0, y: 10, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          className="mt-6 p-4 rounded-xl glass-panel border border-red-500/40 text-red-200 text-sm max-w-md w-full flex items-start gap-3 shadow-[0_8px_30px_rgba(239,68,68,0.2)]"
        >
          <ShieldAlert className="w-5 h-5 text-red-500 shrink-0" />
          <span className="font-medium leading-relaxed">{validationError}</span>
        </motion.div>
      )}

      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        onChange={handleFileChange}
        className="sr-only"
        accept="image/*,video/*,audio/*,.pdf,.doc,.docx"
        aria-label="Upload evidence file"
      />
    </motion.div>
  );
}
