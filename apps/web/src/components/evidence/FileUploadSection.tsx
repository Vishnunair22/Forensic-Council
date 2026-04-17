"use client";

import { useRef, useMemo, useEffect, useState } from "react";
import Image from "next/image";
import { 
 RotateCcw, 
 ArrowRight, 
 UploadCloud, 
 FileAudio, 
 ShieldAlert, 
 ScanLine 
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
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
  const [fileHash, setFileHash] = useState<string | null>(null);

  const computeHash = async (f: File) => {
    try {
      const buf = await f.arrayBuffer();
      const digest = await crypto.subtle.digest("SHA-256", buf);
      return Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, "0")).join("");
    } catch {
      return null;
    }
  };

  useEffect(() => {
    if (file) {
      computeHash(file).then(setFileHash);
    } else {
      setFileHash(null);
    }
  }, [file]);

  const fileSizeMb = file ? file.size / 1024 / 1024 : 0;
  const fileSizeColor = fileSizeMb > 200 ? "text-rose-400" : fileSizeMb > 50 ? "text-amber-400" : "text-white/40";

 const filePreviewUrl = useMemo(() => {
  if (!file) return null;
  if (file.type.startsWith("image/") || file.type.startsWith("video/")) {
   return URL.createObjectURL(file);
  }
  return null;
 }, [file]);

 useEffect(() => {
  return () => {
   if (filePreviewUrl) URL.revokeObjectURL(filePreviewUrl);
  };
 }, [filePreviewUrl]);

 return (
  <div className="flex flex-col items-center justify-center min-h-[75vh] w-full max-w-2xl mx-auto px-4">
   {/* Title Section */}
   <motion.div 
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    className="text-center mb-12"
   >
    <div className="inline-flex items-center gap-3 px-4 py-2 rounded-full mb-8 bg-cyan-500/5 border border-cyan-500/10">
     <span className="relative flex h-2 w-2">
      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-500 opacity-60" />
      <span className="relative inline-flex rounded-full h-full w-full bg-cyan-500" />
     </span>
     <span className=" tracking-widest font-bold text-xs text-cyan-400 font-mono">
      Evidence Upload
     </span>
    </div>

    <h1 className="text-4xl md:text-5xl font-black mb-4 tracking-tighter text-white leading-tight font-heading">
     Initiate Investigation
    </h1>

    <p className="text-white/40 text-sm font-medium max-w-sm mx-auto leading-relaxed">
     Upload an image, video, or audio file to begin forensic analysis.
    </p>
   </motion.div>

   {/* File Area */}
   <AnimatePresence mode="wait">
    {file ? (
     <motion.div
      key="preview"
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
      className="w-full rounded-3xl overflow-hidden glass-panel border-white/10 group shadow-[0_32px_64px_rgba(0,0,0,0.4)]"
     >
      {/* Preview Viewport */}
      <div className="relative w-full aspect-video bg-black/40 overflow-hidden">
       {file.type.startsWith("image/") && filePreviewUrl && (
        <div className="relative w-full h-full">
         <Image
          src={filePreviewUrl}
          alt={file.name}
          fill
          className="object-contain"
          unoptimized={true}
         />
        </div>
       )}
        {file.type.startsWith("video/") && (
         <video
          src={filePreviewUrl ?? ""}
          className="w-full h-full object-contain"
          controls
         />
       )}
       {!file.type.startsWith("image/") && !file.type.startsWith("video/") && (
        <div className="flex flex-col items-center justify-center h-full gap-4">
         <div className="w-20 h-20 rounded-2xl flex items-center justify-center bg-white/5 border border-white/10">
          <FileAudio className="w-10 h-10 text-cyan-500" />
         </div>
        </div>
       )}

       {/* Overlay Metadata */}
       <div className="absolute bottom-0 inset-x-0 p-6 bg-gradient-to-t from-black/80 to-transparent z-10">
        <div className="flex items-center justify-between">
         <div className="flex flex-col">
          <span className="text-xs font-bold text-white font-mono truncate max-w-xs">{file.name}</span>
           <span className={`text-[10px] ${fileSizeColor} font-bold tracking-widest mt-1`}>
            {fileSizeMb.toFixed(2)} MB · {(file.type.split('/')[1] ?? file.type).toUpperCase()}
           </span>
           {fileHash && (
            <span className="text-[9px] font-mono text-white/15 tracking-tight mt-0.5 truncate max-w-xs block" title={fileHash}>
             SHA-256: {fileHash.slice(0, 16)}…{fileHash.slice(-8)}
            </span>
           )}
         </div>
        </div>
       </div>
      </div>

      {/* Actions */}
      <div className="p-6 grid grid-cols-2 gap-4 bg-white/[0.02]">
       <button
        onClick={onClear}
        disabled={isUploading}
        className="flex items-center justify-center gap-2 py-4 rounded-xl border border-white/10 bg-white/5 text-white/50 text-[10px] font-black tracking-widest hover:bg-white/10 transition-all active:scale-95"
       >
        <RotateCcw className="w-3.5 h-3.5" />
        Discard
       </button>
       <button
        onClick={() => onUpload(file)}
        disabled={isUploading}
        className="flex items-center justify-center gap-3 py-4 rounded-xl bg-cyan-600 text-white text-sm font-bold tracking-widest hover:bg-cyan-500 transition-all shadow-[0_0_20px_rgba(8,145,178,0.3)] active:scale-95"
       >
        {isUploading ? (
         <>
          <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" aria-hidden="true" />
          Uploading…
         </>
        ) : (
         <>
          <ScanLine className="w-4 h-4" aria-hidden="true" />
          Start Analysis
          <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
         </>
        )}
       </button>
      </div>
     </motion.div>
    ) : (
     <motion.div
      key="dropzone"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      role="button"
      tabIndex={0}
      aria-label="Upload evidence file. Click or drag and drop."
      className={clsx(
       "w-full rounded-3xl transition-all duration-500 cursor-pointer overflow-hidden relative border-2 border-dashed group",
       isDragging ? "bg-cyan-500/10 border-cyan-500/40 scale-[1.01]" : "bg-white/[0.01] border-white/5 hover:border-white/20 hover:bg-white/[0.02]"
      )}
      onClick={() => fileInputRef.current?.click()}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInputRef.current?.click(); } }}
      onDragEnter={(e) => { e.preventDefault(); onDragEnter(); }}
      onDragOver={(e) => { e.preventDefault(); if (!isDragging) onDragEnter(); }}
      onDragLeave={onDragLeave}
      onDrop={(e) => {
       e.preventDefault();
       onDragLeave();
       const f = e.dataTransfer.files?.[0];
       if (f) onFileDrop(f);
      }}
     >
      <div className="py-20 flex flex-col items-center gap-6">
       <div className={clsx(
        "w-20 h-20 rounded-3xl flex items-center justify-center transition-all duration-500 border shadow-2xl",
        isDragging ? "bg-cyan-500/20 border-cyan-400/50 text-cyan-400 rotate-12 scale-110" : "bg-white/5 border-white/10 text-white/20 group-hover:text-cyan-400 group-hover:bg-cyan-500/10 group-hover:border-cyan-500/30 group-hover:scale-110"
       )}>
        <UploadCloud className="w-8 h-8" strokeWidth={1.5} />
       </div>

       <div className="text-center space-y-2">
        <p className="text-xl font-black text-white tracking-tighter font-heading">
         {isDragging ? "Drop to Upload" : "Upload Evidence File"}
        </p>
        <p className="text-sm font-medium text-white/40">
         Drag &amp; drop or click to browse
        </p>
       </div>

       <div className="flex gap-2 mt-4 flex-wrap justify-center">
        {["Image", "Video", "Audio"].map((t) => (
         <span key={t} className="px-3 py-1 rounded-lg bg-white/[0.03] border border-white/[0.07] text-xs font-semibold text-white/50">
          {t}
         </span>
        ))}
       </div>
      </div>
     </motion.div>
    )}
   </AnimatePresence>

   {/* Validation Error */}
   <AnimatePresence>
    {validationError && (
     <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95 }}
      className="mt-8 p-5 rounded-3xl glass-panel border-rose-500/20 bg-rose-500/[0.04] flex items-start gap-4 max-w-md shadow-2xl shadow-rose-950/20"
     >
      <ShieldAlert className="w-6 h-6 text-rose-500 shrink-0 mt-0.5" />
      <div className="space-y-1">
       <span className="text-[10px] font-bold text-white/40 tracking-[0.2em]">Forensic Logic</span>
       <p className="text-xs text-rose-200/60 font-medium leading-relaxed">{validationError}</p>
      </div>
     </motion.div>
    )}
   </AnimatePresence>

   <input
    ref={fileInputRef}
    type="file"
    onChange={(e) => {
     const f = e.target.files?.[0];
     if (f) onFileSelect(f);
    }}
    className="sr-only"
    accept="image/*,video/*,audio/*"
   />
  </div>
 );
}
