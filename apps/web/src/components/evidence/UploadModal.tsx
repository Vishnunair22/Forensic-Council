"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { createPortal } from "react-dom";
import { motion } from "framer-motion";
import { X, UploadCloud, FileImage, FileVideo, FileAudio, FileText } from "lucide-react";

const overlayVariants = {
 hidden: { opacity: 0 },
 visible: { opacity: 1, transition: { duration: 0.2 } },
 exit: { opacity: 0, transition: { duration: 0.2 } },
};

const scaleIn = {
 hidden: { opacity: 0, scale: 0.95, y: -10 },
 visible: {
  opacity: 1,
  scale: 1,
  y: 0,
  transition: { duration: 0.4, ease: [0.22, 1, 0.36, 1] as const },
 },
 exit: { opacity: 0, scale: 0.95, y: -10, transition: { duration: 0.2 } },
};

interface UploadModalProps {
 onClose: () => void;
 onFileSelected: (f: File) => void;
}

export function UploadModal({ onClose, onFileSelected }: UploadModalProps) {
 const [isDragging, setIsDragging] = useState(false);
 const fileInputRef = useRef<HTMLInputElement>(null);
 const modalRef = useRef<HTMLDivElement>(null);
 const previousFocusRef = useRef<HTMLElement | null>(null);
 const [mounted, setMounted] = useState(false);

 useEffect(() => {
  setMounted(true);
 }, []);

 const handleFile = useCallback(
  (f: File) => {
   onFileSelected(f);
  },
  [onFileSelected],
 );

 useEffect(() => {
  const originalBodyOverflow = document.body.style.overflow;
  const originalHtmlOverflow = document.documentElement.style.overflow;
  document.body.style.overflow = "hidden";
  document.documentElement.style.overflow = "hidden";
  previousFocusRef.current = document.activeElement as HTMLElement;
  if (modalRef.current) {
   const focusable = modalRef.current.querySelector<HTMLElement>(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
   );
   focusable?.focus();
  }
  const handleKeyDown = (e: KeyboardEvent) => {
   if (e.key === "Escape") {
    onClose();
   }
   if (e.key === "Tab") {
    const focusableElements = modalRef.current?.querySelectorAll<HTMLElement>(
     'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    if (!focusableElements || focusableElements.length === 0) return;
    const firstFocusable = focusableElements[0];
    const lastFocusable = focusableElements[focusableElements.length - 1];
    if (e.shiftKey) {
     if (document.activeElement === firstFocusable) {
      e.preventDefault();
      lastFocusable.focus();
     }
    } else {
     if (document.activeElement === lastFocusable) {
      e.preventDefault();
      firstFocusable.focus();
     }
    }
   }
  };
  document.addEventListener("keydown", handleKeyDown);
  return () => {
   document.body.style.overflow = originalBodyOverflow || "unset";
   document.documentElement.style.overflow = originalHtmlOverflow || "auto";
   document.removeEventListener("keydown", handleKeyDown);
   previousFocusRef.current?.focus();
  };
 }, [onClose]);

 const modalContent = (
  <motion.div
   className="fixed top-0 left-0 w-full h-full z-[9999] flex items-center justify-center p-4 backdrop-blur-2xl touch-none"
   style={{ background: "rgba(0,0,0,0.85)" }}
   variants={overlayVariants}
   initial="hidden"
   animate="visible"
   exit="exit"
   onClick={onClose}
   role="dialog"
   aria-modal="true"
   aria-labelledby="upload-modal-title"
  >
   <motion.div
    ref={modalRef}
    className="relative w-full max-w-lg"
    variants={scaleIn}
    initial="hidden"
    animate="visible"
    exit="exit"
    onClick={(e) => e.stopPropagation()}
   >
    <div className="rounded-2xl overflow-hidden glass-panel shadow-2xl relative">
     <div className="scan-line-overlay opacity-30 pointer-events-none" />
     <div className="relative p-10 z-20">
      <button
       onClick={onClose}
       className="absolute top-8 right-8 p-2 rounded-xl cursor-pointer hover:bg-white/[0.05] transition-colors border border-white/[0.05] z-30"
       aria-label="Close upload modal"
      >
       <X className="w-5 h-5 text-white/50" />
      </button>

      <motion.div
       initial={{ opacity: 0, y: 16 }}
       animate={{ opacity: 1, y: 0 }}
       transition={{ delay: 0.1, duration: 0.4 }}
      >
       <div className="mb-10 text-center flex flex-col items-center">
        <h3 id="upload-modal-title" className="text-3xl font-black text-white tracking-tight font-heading">
         Ingestion Gateway
        </h3>
        <p className="text-sky-400/50 text-[11px] font-mono font-bold tracking-[0.25em] mt-2 text-center">
         Secure Forensic Intake
        </p>
       </div>

       <motion.label
        htmlFor="dropzone-file"
        tabIndex={0}
        aria-label="Upload evidence — click or press Enter to browse, or drag and drop a file"
        className="group relative rounded-3xl border p-14 text-center cursor-pointer overflow-hidden transition-all duration-500"
        style={{
         borderColor: isDragging
          ? "rgba(34,211,238,0.4)"
          : "rgba(255,255,255,0.03)",
         background: isDragging
          ? "rgba(34,211,238,0.03)"
          : "rgba(255,255,255,0.01)",
        }}
        whileHover={{
         borderColor: "rgba(34,211,238,0.25)",
         background: "rgba(34,211,238,0.02)",
        }}
        onDragOver={(e) => {
         e.preventDefault();
         setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
         e.preventDefault();
         setIsDragging(false);
         const f = e.dataTransfer.files[0];
         if (f) handleFile(f);
        }}
       >
        <div className="absolute inset-0 bg-gradient-to-b from-cyan-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none duration-700" />
        <div className="relative z-10">
         <motion.div
          className="w-20 h-20 rounded-2xl bg-cyan-500/[0.03] flex items-center justify-center mx-auto mb-6 border border-cyan-500/10"
          whileHover={{ scale: 1.1, rotate: 5 }}
          transition={{ type: "spring", stiffness: 400, damping: 10 }}
         >
          <UploadCloud className="w-10 h-10 text-cyan-400/50" />
         </motion.div>
         <p className="text-xl font-bold text-white/90 mb-3 tracking-tight">
          Drop evidence here or{" "}
          <span className="text-cyan-400/80 underline underline-offset-8 decoration-cyan-400/20 hover:text-cyan-400 transition-colors">
           browse
          </span>
         </p>
         <div className="flex items-center justify-center gap-4 opacity-20 group-hover:opacity-40 transition-opacity duration-700">
          <FileImage className="w-4 h-4" />
          <FileVideo className="w-4 h-4" />
          <FileAudio className="w-4 h-4" />
          <FileText className="w-4 h-4" />
         </div>
        </div>
        <input
         id="dropzone-file"
         ref={fileInputRef}
         type="file"
         className="hidden"
         accept="image/*,audio/*,video/*"
         aria-label="Select evidence file"
         onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) handleFile(f);
         }}
        />
       </motion.label>

       <div className="mt-10 flex flex-col items-center gap-3 px-2 text-center">
        <div className="flex items-center justify-center gap-3">
         <div className="w-1.5 h-1.5 rounded-full bg-cyan-500 shadow-[0_0_8px_rgba(34,211,238,0.5)]" />
         <p className="text-[11px] font-mono font-bold text-white/40 tracking-widest">
          Supported: IMG, VID, AUD, DOC
         </p>
        </div>
        <p className="text-[10px] text-white/20 font-mono tracking-tight leading-relaxed max-w-[280px] mx-auto">
         Maximum file size: 50 MB &middot; SHA-256 integrity check
         performed automatically on ingestion.
        </p>
       </div>
      </motion.div>
     </div>
    </div>
   </motion.div>
  </motion.div>
 );

 if (!mounted) return null;

 return createPortal(modalContent, document.body);
}
