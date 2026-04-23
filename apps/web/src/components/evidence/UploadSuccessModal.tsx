"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { motion } from "framer-motion";
import { CheckCircle2, FileText, Image as ImageIcon, Video as VideoIcon } from "lucide-react";

export interface UploadSuccessModalProps {
  file: File;
  onNewUpload: () => void;
  onStartAnalysis: () => void;
}

export function UploadSuccessModal({ file, onNewUpload, onStartAnalysis }: UploadSuccessModalProps) {
  const [mounted, setMounted] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    setMounted(true);
    
    // Create preview URL for images and videos
    if (file.type.startsWith("image/") || file.type.startsWith("video/")) {
      const url = URL.createObjectURL(file);
      setPreviewUrl(url);
      return () => URL.revokeObjectURL(url);
    }

    // Lock scroll on mount, unlock on unmount
    const originalBodyOverflow = document.body.style.overflow;
    const originalHtmlOverflow = document.documentElement.style.overflow;
    
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";
    
    return () => {
      document.body.style.overflow = originalBodyOverflow || "unset";
      document.documentElement.style.overflow = originalHtmlOverflow || "unset";
    };
  }, [file]);

  if (!mounted) return null;

  const isImage = file.type.startsWith("image/");
  const isVideo = file.type.startsWith("video/");

  return createPortal(
    <motion.div
      initial={{ opacity: 0, backdropFilter: "blur(0px)" }}
      animate={{ opacity: 1, backdropFilter: "blur(12px)" }}
      exit={{ opacity: 0, backdropFilter: "blur(0px)", transition: { delay: 0.5 } }}
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 p-4"
    >
      <div className="relative w-full max-w-xl" onClick={(e) => e.stopPropagation()}>
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.95 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
          className="relative z-20 bg-white/[0.04] backdrop-blur-xl border border-white/10 rounded-3xl p-10 shadow-[0_0_80px_rgba(0,0,0,0.9)] overflow-hidden"
        >
          <div className="flex flex-col items-center text-center gap-6">
            <motion.div 
              initial={{ scale: 0.5, opacity: 0 }} 
              animate={{ scale: 1, opacity: 1 }} 
              transition={{ type: "spring", bounce: 0.5, delay: 0.2 }}
              className="w-16 h-16 rounded-full bg-primary/10 border border-primary/20 text-primary flex items-center justify-center relative"
            >
              <CheckCircle2 className="w-8 h-8" />
            </motion.div>
            
            <div className="space-y-4 w-full">
              <h2 className="text-2xl font-black text-white">Evidence Ready</h2>
              
              <div className="relative rounded-2xl bg-black/40 border border-white/10 overflow-hidden group">
                {/* Preview Container */}
                <div className="aspect-video w-full bg-white/[0.02] flex items-center justify-center overflow-hidden">
                  {isImage && previewUrl ? (
                    <img 
                      src={previewUrl} 
                      alt="Preview" 
                      className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105" 
                    />
                  ) : isVideo && previewUrl ? (
                    <video 
                      src={previewUrl} 
                      className="w-full h-full object-cover" 
                      autoPlay 
                      muted 
                      loop 
                      playsInline 
                    />
                  ) : (
                    <div className="flex flex-col items-center gap-3 text-white/20">
                      <FileText className="w-12 h-12" strokeWidth={1} />
                      <span className="text-xs font-mono tracking-widest uppercase">No Preview</span>
                    </div>
                  )}
                  
                  {/* Glass Overlay for info */}
                  <div className="absolute inset-x-0 bottom-0 p-4 bg-gradient-to-t from-black/80 to-transparent backdrop-blur-sm border-t border-white/5">
                    <p className="text-sm font-mono text-white/90 truncate mb-1">
                      {file.name}
                    </p>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-mono font-bold text-primary bg-primary/10 px-2 py-0.5 rounded border border-primary/20">
                        {(file.size / (1024 * 1024)).toFixed(2)} MB
                      </span>
                      <span className="text-[10px] font-mono text-white/40 uppercase tracking-wider">
                        {file.type.split("/")[1] || "Binary"}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex w-full gap-4 mt-2">
              <button
                onClick={onNewUpload}
                className="flex-1 px-8 py-4 min-h-[48px] rounded-full border border-white/15 text-white/70 hover:border-white/30 hover:text-white hover:bg-white/[0.05] transition-all text-sm font-bold tracking-wide"
              >
                Reselect
              </button>
              <button
                onClick={onStartAnalysis}
                className="flex-1 group px-8 py-4 min-h-[48px] rounded-full bg-primary text-black font-bold text-sm tracking-wide hover:bg-primary/90 active:scale-[0.98] transition-all duration-300 shadow-[0_0_30px_rgba(0,255,65,0.25)] hover:shadow-[0_0_50px_rgba(0,255,65,0.4)]"
              >
                Begin Analysis
              </button>
            </div>
          </div>
        </motion.div>
      </div>
    </motion.div>,
    document.body
  );
}
