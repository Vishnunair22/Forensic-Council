"use client";

import { useRef, useMemo, useEffect, useState, useCallback } from "react";
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
import { ALLOWED_MIME_TYPES } from "@/lib/constants";

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

  const computeHash = useCallback(async (f: File) => {
    try {
      const buf = await f.arrayBuffer();
      const digest = await crypto.subtle.digest("SHA-256", buf);
      return Array.from(new Uint8Array(digest))
        .map((b) => b.toString(16).padStart(2, "0"))
        .join("");
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    let isActive = true;
    if (file) {
      computeHash(file).then(hash => {
        if (isActive) setFileHash(hash);
      });
    } else {
      setFileHash(null);
    }
    return () => { isActive = false; };
  }, [file, computeHash]);

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
     <div className="inline-flex items-center gap-3 px-4 py-2 rounded-full mb-8 bg-[var(--color-success-light)]/[0.08] border border-[var(--color-success-light)]/20">
      <span className="relative flex h-2 w-2">
       <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--color-success-light)] opacity-60" />
       <span className="relative inline-flex rounded-full h-full w-full bg-[var(--color-success-light)]" />
      </span>
      <span className="tracking-[0.2em] font-bold text-[10px] text-[var(--color-success-light)] font-mono uppercase">
       Evidence_Ingestion
      </span>
     </div>

     <h1 className="text-5xl md:text-6xl font-black mb-6 tracking-tight text-white leading-none font-heading">
      Forensic Pipeline
     </h1>

     <p className="text-white/40 text-lg font-medium max-w-sm mx-auto leading-relaxed">
      Submit digital media for multi-agent cryptographic verification.
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
       className="w-full glass-panel overflow-hidden group shadow-[0_32px_64px_rgba(0,0,0,0.6)]"
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
           <FileAudio className="w-10 h-10 text-[var(--color-success-light)]" />
          </div>
         </div>
        )}

        {/* Overlay Metadata */}
        <div className="absolute bottom-0 inset-x-0 p-8 bg-gradient-to-t from-black/90 to-transparent z-10">
         <div className="flex items-center justify-between">
          <div className="flex flex-col">
           <span className="text-sm font-bold text-white font-mono truncate max-w-xs">{file.name}</span>
            <span className={`text-[10px] ${fileSizeColor} font-bold tracking-widest mt-1 uppercase`}>
             {fileSizeMb.toFixed(2)} MB · {(file.type.split('/')[1] ?? file.type).toUpperCase()}
            </span>
            {fileHash && (
             <span className="text-[10px] font-mono text-white/30 break-all tracking-tight mt-1 max-w-xs block" title={fileHash}>
              HASH: {fileHash.slice(0, 24)}...
             </span>
            )}
          </div>
         </div>
        </div>
       </div>

       {/* Actions */}
       <div className="p-6 grid grid-cols-2 gap-4 bg-white/[0.02]">
        <button
         onClick={() => {
           if (fileInputRef.current) fileInputRef.current.value = "";
           onClear();
         }}
         disabled={isUploading}
         className="flex items-center justify-center gap-2 py-4 min-h-[48px] rounded-full border border-white/10 text-white/50 hover:border-white/20 hover:text-white text-sm font-bold tracking-wide hover:bg-white/[0.05] transition-all"
        >
         <RotateCcw className="w-3.5 h-3.5" />
         Discard
        </button>
        <button
         onClick={() => onUpload(file)}
         disabled={isUploading}
         className="btn-horizon-primary"
        >
         {isUploading ? (
          <>
           <div className="w-4 h-4 border-2 border-black/30 border-t-black rounded-full animate-spin" aria-hidden="true" />
           Initializing…
          </>
         ) : (
          <>
           <ScanLine className="w-4 h-4" aria-hidden="true" />
           Start Analysis
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
        "w-full glass-panel transition-all duration-500 cursor-pointer overflow-hidden relative border-2 border-dashed group p-1",
        isDragging ? "border-[var(--color-success-light)]/50 bg-[var(--color-success-light)]/5 scale-[1.01]" : "border-white/10 hover:border-[var(--color-success-light)]/30 hover:bg-white/[0.02]"
       )}
       onClick={() => fileInputRef.current?.click()}
       onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInputRef.current?.click(); } }}
       onDragEnter={(e) => { e.preventDefault(); onDragEnter(); }}
       onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; }}
       onDragLeave={onDragLeave}
       onDrop={(e) => {
        e.preventDefault();
        onDragLeave();
        const f = e.dataTransfer.files?.[0];
        if (f) onFileDrop(f);
       }}
      >
       <div className="py-24 flex flex-col items-center gap-8">
        <div className={clsx(
         "w-24 h-24 rounded-[2rem] flex items-center justify-center transition-all duration-500 border shadow-2xl",
         isDragging ? "bg-[var(--color-success-light)]/20 border-[var(--color-success-light)]/40 text-[var(--color-success-light)] scale-110" : "bg-white/5 border-white/5 text-white/10 group-hover:text-[var(--color-success-light)] group-hover:bg-[var(--color-success-light)]/10 group-hover:border-[var(--color-success-light)]/20 group-hover:scale-105"
        )}>
         <UploadCloud className="w-10 h-10" strokeWidth={1.5} />
        </div>

        <div className="text-center space-y-3">
         <p className="text-2xl font-black text-white tracking-tighter font-heading">
          {isDragging ? "Process Evidence" : "Load Media File"}
         </p>
         <p className="text-base font-medium text-white/30">
          Drag &amp; drop or click to securely upload
         </p>
        </div>

        <div className="flex gap-3 mt-4 flex-wrap justify-center">
         {["Image", "Video", "Audio"].map((t) => (
          <span key={t} className="px-4 py-1.5 rounded-full bg-white/[0.03] border border-white/[0.07] text-[10px] font-bold uppercase tracking-widest text-white/30">
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
      className="mt-8 p-5 rounded-3xl bg-danger/[0.05] backdrop-blur-xl border border-danger/20 flex items-start gap-4 max-w-md shadow-2xl shadow-rose-950/20"
     >
      <ShieldAlert className="w-6 h-6 text-danger shrink-0 mt-0.5" />
      <div className="space-y-1">
       <span className="text-xs font-bold text-danger/80 tracking-wide">Forensic Logic</span>
       <p className="text-sm text-white/80 font-medium leading-relaxed">{validationError}</p>
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
    accept={Array.from(ALLOWED_MIME_TYPES).join(",")}
   />
  </div>
 );
}
