"use client";

import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { motion } from "framer-motion";
import { RefreshCw, ArrowRight, FileImage, FileAudio, FileVideo, FileText } from "lucide-react";
import { useSound } from "@/hooks/useSound";

const overlayVariants = {
 hidden: { opacity: 0 },
 visible: { opacity: 1, transition: { duration: 0.2 } },
 exit: { opacity: 0, transition: { duration: 0.2 } },
};

const scaleIn = {
 hidden: { opacity: 0, scale: 0.95, y: 10 },
 visible: {
  opacity: 1,
  scale: 1,
  y: 0,
  transition: { duration: 0.4, ease: [0.22, 1, 0.36, 1] as const },
 },
 exit: { opacity: 0, scale: 0.95, y: 10, transition: { duration: 0.2 } },
};

interface UploadSuccessModalProps {
 file: File;
 onNewUpload: () => void;
 onStartAnalysis: () => void;
}

export function UploadSuccessModal({
 file,
 onNewUpload,
 onStartAnalysis,
}: UploadSuccessModalProps) {
 const [previewUrl, setPreviewUrl] = useState<string | null>(null);
 const [hasError, setHasError] = useState(false);
 const modalRef = useRef<HTMLDivElement>(null);
 const previousFocusRef = useRef<HTMLElement | null>(null);
 const { playSound } = useSound();
 const [mounted, setMounted] = useState(false);

 useEffect(() => {
  setMounted(true);
 }, []);

 useEffect(() => {
  playSound("success");
 }, [playSound]);

 useEffect(() => {
  if (!file) {
   setPreviewUrl(null);
   return;
  }

  const isMedia =
   file.type.startsWith("image/") ||
   file.type.startsWith("video/") ||
   /\.(jpe?g|png|gif|bmp|webp|jfif|mp4|webm|mov|ogg)$/i.test(file.name);

  if (isMedia) {
   const url = URL.createObjectURL(file);
   setPreviewUrl(url);
   setHasError(false);
   return () => {
    URL.revokeObjectURL(url);
   };
  } else {
   setPreviewUrl(null);
  }
 }, [file]);

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
    onStartAnalysis();
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
 }, [onStartAnalysis]);

 const isVideo =
  file.type.startsWith("video/") || /\.(mp4|webm|mov|ogg)$/i.test(file.name);
 const FileTypeIcon = file.type.startsWith("image/")
  ? FileImage
  : file.type.startsWith("audio/")
   ? FileAudio
   : isVideo
    ? FileVideo
    : FileText;

 const modalContent = (
  <motion.div
   className="fixed top-0 left-0 w-full h-full z-[9999] flex items-center justify-center p-4 backdrop-blur-2xl touch-none"
   style={{ background: "rgba(0,0,0,0.85)" }}
   variants={overlayVariants}
   initial="hidden"
   animate="visible"
   exit="exit"
   role="dialog"
   aria-modal="true"
   aria-labelledby="upload-success-title"
  >
   <motion.div
    ref={modalRef}
    className="glass-panel relative w-full max-w-sm overflow-hidden rounded-2xl p-10 shadow-2xl"
    variants={scaleIn}
    initial="hidden"
    animate="visible"
    exit="exit"
   >
    <div className="scan-line-overlay opacity-20" />
    <motion.div
     className="w-32 h-32 rounded-[2rem] mx-auto mb-10 overflow-hidden flex items-center justify-center relative z-10 border border-white/[0.08] bg-white/[0.02] shadow-2xl"
     animate={{
      y: [0, -5, 0],
      rotate: [0, 1, 0, -1, 0],
     }}
     transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}
    >
     {previewUrl && !hasError ? (
      isVideo ? (
       <video
        key={previewUrl}
        src={previewUrl}
        className="w-full h-full object-cover transition-opacity duration-500"
        muted
        loop
        autoPlay
        playsInline
        onError={() => setHasError(true)}
        aria-hidden="true"
       />
      ) : (
       /* eslint-disable-next-line @next/next/no-img-element */
       <img
        key={previewUrl}
        src={previewUrl}
        alt={`Evidence preview: ${file.name}`}
        className="w-full h-full object-cover transition-opacity duration-500"
        onError={() => setHasError(true)}
       />
      )
     ) : (
      <div className="flex flex-col items-center gap-3">
       <div className="p-4 rounded-3xl bg-cyan-500/5 border border-cyan-500/10">
        <FileTypeIcon
         className="w-10 h-10 text-cyan-400/60"
         aria-hidden="true"
        />
       </div>
      </div>
     )}
    </motion.div>

    <motion.div
     initial={{ opacity: 0, y: 20 }}
     animate={{ opacity: 1, y: 0 }}
     transition={{ delay: 0.1, duration: 0.5, ease: "easeOut" }}
     className="relative z-10"
    >
     <div className="flex flex-col items-center mb-10">
      <div className="inline-flex items-center gap-3 mb-6 px-5 py-2 rounded-full bg-emerald-500/5 border border-emerald-500/10 backdrop-blur-sm">
       <motion.div
        className="w-2.5 h-2.5 rounded-full bg-emerald-400/60 shadow-[0_0_15px_rgba(52,211,153,0.3)]"
        animate={{ opacity: [1, 0.5, 1] }}
        transition={{ duration: 3, repeat: Infinity }}
       />
       <span className="text-[10px] font-mono font-black text-emerald-400/70 tracking-[0.2em] ">
        Integrity Verified
       </span>
      </div>
      
      <h3 id="upload-success-title" className="text-white text-2xl font-black truncate max-w-full px-4 mb-4 tracking-tight font-heading text-center">
       {file.name}
      </h3>
     </div>

     <div className="flex flex-col sm:flex-row gap-4 mt-6">
      <button
       onClick={onNewUpload}
       className="btn-pill-secondary flex-1 !px-4"
      >
       <RefreshCw className="w-4 h-4 group-hover:rotate-180 transition-transform duration-700" />
       <span>Reset</span>
      </button>

      <button
       onClick={onStartAnalysis}
       className="btn-pill-primary flex-[1.6] group !px-4"
      >
       <span className="text-[11px] tracking-[0.1em] font-black">Analyze</span>
       <ArrowRight className="w-4 h-4 group-hover:translate-x-1.5 transition-transform duration-500" />
      </button>
     </div>
    </motion.div>
   </motion.div>
  </motion.div>
 );

 if (!mounted) return null;

 return createPortal(modalContent, document.body);
}
