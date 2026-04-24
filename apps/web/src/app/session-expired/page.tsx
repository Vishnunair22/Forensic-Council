"use client";

import { motion } from "framer-motion";
import { ShieldX, LogIn } from "lucide-react";
import { useRouter } from "next/navigation";

export default function SessionExpiredPage() {
  const router = useRouter();

  return (
    <div className="min-h-screen bg-[#020617] flex flex-col items-center justify-center p-6 text-center relative overflow-hidden">
      {/* Background Micro-particles / Ambient */}
      <div className="absolute inset-0 bg-primary/[0.02] pointer-events-none" />
      
      <motion.div
        initial={{ opacity: 0, scale: 0.98, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        className="relative max-w-md w-full"
      >
        <div className="horizon-card p-1 border-warning/20">
          <div className="bg-[#020617] rounded-[inherit] p-10 flex flex-col items-center">
            
            {/* Aperture Node (Warning) */}
            <div className="relative w-20 h-20 mb-8 flex items-center justify-center">
              <motion.div 
                animate={{ rotate: 360 }}
                transition={{ duration: 15, repeat: Infinity, ease: "linear" }}
                className="absolute inset-0 rounded-full border border-warning/20 border-dashed"
              />
              <ShieldX className="w-8 h-8 text-warning relative z-10" />
            </div>

            <h1 className="text-3xl font-heading font-bold text-white mb-4">Session Expired</h1>

            <p className="text-sm font-medium text-white/30 mb-10 leading-relaxed text-center">
              Your investigator session has reached its TTL (Time To Live). 
              For security reasons, active neural links must be re-authenticated periodically.
            </p>

            <button
              onClick={() => router.push("/")}
              className="w-full btn-horizon-primary py-4 text-xs flex items-center justify-center gap-3"
            >
              <LogIn className="w-4 h-4" />
              Re-Authenticate Session
            </button>
            
            {/* HUD Marker */}
            <div className="mt-10 text-[9px] font-mono text-white/10 tracking-[0.4em] uppercase">
              SECURITY_VOID // CODE_401
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
