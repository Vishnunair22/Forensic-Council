"use client";

import { useEffect, useState, useRef } from "react";
import { createPortal } from "react-dom";
import { motion } from "framer-motion";
import { X, UploadCloud } from "lucide-react";

export function UploadModal({ onClose, onFileSelected }: any) {
  const [mounted, setMounted] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setMounted(true);
    // Lock scroll on mount, unlock on unmount
    const originalBodyOverflow = document.body.style.overflow;
    const originalHtmlOverflow = document.documentElement.style.overflow;
    
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";
    
    return () => {
      document.body.style.overflow = originalBodyOverflow || "unset";
      document.documentElement.style.overflow = originalHtmlOverflow || "unset";
    };
  }, []);

  if (!mounted) return null;

  return createPortal(
    <motion.div
      initial={{ opacity: 0, backdropFilter: "blur(0px)" }}
      animate={{ opacity: 1, backdropFilter: "blur(12px)" }}
      exit={{ opacity: 0, backdropFilter: "blur(0px)", transition: { delay: 0.3 } }}
      // Click outside to close
      onClick={onClose}
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 p-4"
    >
      {/* 3D Perspective Wrapper */}
      <div 
        className="relative w-full max-w-xl" 
        style={{ perspective: "1500px" }}
        onClick={(e) => e.stopPropagation()} // Prevent closing when clicking inside
      >
        
        {/* The Cyber-Flap (Opens upward) */}
        <motion.div
          initial={{ rotateX: 0, opacity: 1 }}
          animate={{ rotateX: 180, opacity: 0 }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
          style={{ transformOrigin: "top" }}
          className="absolute inset-0 z-30 bg-gradient-to-b from-black to-black/90 border border-primary/40 rounded-3xl flex items-center justify-center shadow-[0_-20px_50px_rgba(0,255,65,0.15)] pointer-events-none"
        >
          {/* Subtle glowing line on the flap edge */}
          <div className="absolute bottom-0 w-1/2 h-[1px] bg-primary shadow-[0_0_10px_rgba(0,255,65,0.8)]" />
        </motion.div>

        {/* The Modal Content (The inside of the envelope) */}
        <motion.div
          initial={{ y: 20, opacity: 0, scale: 0.95 }}
          animate={{ y: 0, opacity: 1, scale: 1 }}
          exit={{ y: -20, opacity: 0, scale: 0.95 }}
          transition={{ duration: 0.5, delay: 0.15, ease: "easeOut" }}
          className="relative z-40 bg-black/80 backdrop-blur-xl border border-white/10 rounded-3xl p-10 shadow-[0_20px_60px_rgba(0,0,0,0.8)]"
        >
          {/* Close Button */}
          <button 
            onClick={onClose}
            className="absolute top-6 right-6 text-white/40 hover:text-white transition-colors"
            autoFocus
          >
            <X className="w-5 h-5" />
          </button>

          {/* Refined Dropzone UI */}
          <div className="flex flex-col items-center text-center gap-4">
            <div className="w-16 h-16 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center mb-4 shadow-[inset_0_0_20px_rgba(var(--primary),0.1)]">
              <UploadCloud className="w-8 h-8 text-primary" />
            </div>
            <h3 className="text-2xl font-bold tracking-tight text-white">Upload Evidence</h3>
            <p className="text-sm font-medium text-white/50 max-w-sm leading-relaxed">
              Drag and drop digital media or click to browse. The neural protocol accepts image, video, and audio payloads.
            </p>
            
            {/* Input integration - Using ref for reliable trigger */}
            <div 
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setIsDragging(false);
                const f = e.dataTransfer.files[0];
                if (f) onFileSelected(f);
              }}
              className={`mt-8 w-full border-2 border-dashed rounded-2xl p-12 transition-all cursor-pointer group flex items-center justify-center relative ${
                isDragging ? "border-primary bg-primary/5 shadow-[0_0_20px_rgba(var(--primary),0.1)]" : "border-white/10 bg-white/[0.02] hover:border-primary/50"
              }`}
            >
              <span className={`text-xs font-bold tracking-widest uppercase transition-colors ${
                isDragging ? "text-primary" : "text-white/40 group-hover:text-primary"
              }`}>
                {isDragging ? "Drop Payload" : "Select File"}
              </span>
              <input 
                ref={fileInputRef}
                type="file" 
                style={{ display: "none" }}
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
