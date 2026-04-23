"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { motion } from "framer-motion";
import { CheckCircle2, X } from "lucide-react";

export function UploadSuccessModal({ file, onNewUpload, onStartAnalysis }: any) {
  const [mounted, setMounted] = useState(false);

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
      // Overall overlay fade out is delayed to let the envelope close first
      exit={{ opacity: 0, backdropFilter: "blur(0px)", transition: { delay: 0.5 } }}
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 p-4"
    >
      <div className="relative w-full max-w-xl" style={{ perspective: "1500px" }}>
        
        {/* The Cyber-Flap (Closes downward on exit) */}
        <motion.div
          initial={{ rotateX: 180, opacity: 0 }}
          animate={{ rotateX: 180, opacity: 0 }} // Stays open while viewing success
          // The Magic: Folds down and solidifies when exiting (routing to analysis)
          exit={{ rotateX: 0, opacity: 1, transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1] } }} 
          style={{ transformOrigin: "top" }}
          className="absolute inset-0 z-40 bg-gradient-to-b from-primary/10 to-black border border-primary/50 rounded-3xl flex items-center justify-center shadow-[0_20px_50px_rgba(0,255,65,0.2)] pointer-events-none"
        >
           <span className="text-primary font-mono text-sm tracking-[0.3em] shadow-[0_0_10px_rgba(0,255,65,0.8)]">PAYLOAD SECURED</span>
        </motion.div>

        {/* The Success Content */}
        <motion.div
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 10, opacity: 0, scale: 0.95, transition: { duration: 0.3 } }}
          className="relative z-20 bg-black/80 backdrop-blur-xl border border-primary/20 rounded-3xl p-10 shadow-[0_0_60px_rgba(0,255,65,0.05)]"
        >
          <div className="flex flex-col items-center text-center gap-6">
            <motion.div 
              initial={{ scale: 0.5, opacity: 0 }} 
              animate={{ scale: 1, opacity: 1 }} 
              transition={{ type: "spring", bounce: 0.5, delay: 0.2 }}
              className="w-20 h-20 rounded-full bg-primary/10 border border-primary/30 flex items-center justify-center shadow-[0_0_30px_rgba(0,255,65,0.2)]"
            >
              <CheckCircle2 className="w-10 h-10 text-primary" />
            </motion.div>
            
            <div className="space-y-2">
              <h3 className="text-3xl font-bold tracking-tight text-white">Ready for Processing</h3>
              <p className="text-sm font-mono text-white/40 break-all bg-white/[0.02] px-4 py-2 rounded-lg border border-white/5">
                {file.name}
              </p>
            </div>

            <div className="flex w-full gap-4 mt-6">
              <button
                onClick={onNewUpload}
                className="flex-1 py-4 text-xs font-bold tracking-widest uppercase text-white/50 hover:text-white bg-white/5 hover:bg-white/10 rounded-xl transition-all"
              >
                Reselect
              </button>
              <button
                onClick={onStartAnalysis}
                className="flex-1 py-4 text-xs font-bold tracking-widest uppercase text-black bg-primary hover:bg-glow-green rounded-xl shadow-[0_0_20px_rgba(0,255,65,0.3)] hover:shadow-[0_0_40px_rgba(0,255,65,0.5)] transition-all transform hover:scale-[1.02]"
              >
                Analyse
              </button>
            </div>
          </div>
        </motion.div>
      </div>
    </motion.div>,
    document.body
  );
}
