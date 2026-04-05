"use client";

import { motion } from "framer-motion";
import { ShieldX, LogIn } from "lucide-react";
import { useRouter } from "next/navigation";

export default function SessionExpiredPage() {
  const router = useRouter();

  return (
    <div className="min-h-screen text-foreground flex flex-col items-center justify-center p-6 text-center relative overflow-hidden">
      <motion.div
        className="relative max-w-md w-full p-8 rounded-3xl flex flex-col items-center overflow-hidden border border-amber-500/15 bg-white/[0.03]"
        style={{
          backdropFilter: "blur(24px)",
          boxShadow:
            "0 32px 80px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.04)",
        }}
        initial={{ opacity: 0, scale: 0.9, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.34, 1.56, 0.64, 1] }}
      >
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-amber-400/40 to-transparent rounded-t-3xl pointer-events-none" />

        <motion.div
          className="w-16 h-16 bg-amber-500/10 border border-amber-500/25 text-amber-400 rounded-2xl flex items-center justify-center mb-6 shadow-[0_0_28px_rgba(245,158,11,0.15)]"
          animate={{ rotate: [0, -5, 5, 0] }}
          transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
        >
          <ShieldX className="w-8 h-8" aria-hidden="true" />
        </motion.div>

        <h1 className="text-2xl font-bold mb-3">Session Expired</h1>

        <p className="text-slate-400 mb-8 text-sm leading-relaxed text-center">
          Your investigator session has expired or is no longer valid. Please
          return to the dashboard and authenticate again to continue forensic
          analysis.
        </p>

        <motion.button
          onClick={() => router.push("/")}
          className="w-full py-4 rounded-xl font-bold inline-flex items-center justify-center gap-2 text-white border border-cyan-400/30"
          style={{
            background: "linear-gradient(135deg, #0891b2 0%, #22d3ee 100%)",
            boxShadow: "0 0 24px rgba(34,211,238,0.18)",
          }}
          whileHover={{
            scale: 1.02,
            boxShadow: "0 0 32px rgba(34,211,238,0.28)",
          }}
          whileTap={{ scale: 0.98 }}
        >
          <LogIn className="w-5 h-5" aria-hidden="true" />
          Return to Dashboard
        </motion.button>
      </motion.div>
    </div>
  );
}
