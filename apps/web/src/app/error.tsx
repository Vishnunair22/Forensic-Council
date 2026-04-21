"use client";

import { useEffect } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, RefreshCcw, Home } from "lucide-react";
import Link from "next/link";
import { GlobalFooter } from "@/components/ui/GlobalFooter";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Global app error:", error);
  }, [error]);

  return (
    <div className="min-h-screen text-foreground flex flex-col items-center justify-center p-6 text-center relative overflow-hidden bg-background">
      <motion.div
        className="relative max-w-md w-full p-10 rounded-[2.5rem] overflow-hidden flex flex-col items-center z-10 premium-glass border-danger/20"
        initial={{ opacity: 0, scale: 0.9, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.34, 1.56, 0.64, 1] }}
      >
        <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-transparent via-danger/40 to-transparent" />

        <motion.div
          className="w-20 h-20 bg-danger/10 border border-danger/30 rounded-[2rem] flex items-center justify-center mb-8 shadow-[0_0_40px_rgba(244,63,94,0.2)]"
          animate={{ scale: [1, 1.05, 1], opacity: [0.8, 1, 0.8] }}
          transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
        >
          <AlertTriangle className="w-10 h-10 text-danger" />
        </motion.div>

        <h1 className="text-3xl font-black mb-4 text-white tracking-tighter">
          System <span className="text-danger">Interrupted</span>
        </h1>

        <p className="text-slate-400 mb-8 text-sm leading-relaxed text-center">
          An unexpected error occurred during the forensic analysis process. The
          system has safely halted — no data has been lost.
        </p>

        <div className="w-full space-y-4">
          <motion.button
            onClick={() => reset()}
            className="btn-premium w-full py-4 tracking-[0.2em]"
            whileTap={{ scale: 0.98 }}
          >
            <RefreshCcw className="w-4 h-4" />
            Retry Analysis
          </motion.button>

          <Link
            href="/"
            className="btn-outline w-full py-4 tracking-[0.2em]"
          >
            <Home className="w-4 h-4" />
            Return To Hub
          </Link>
        </div>

        {process.env.NODE_ENV === "development" && (
          <div className="mt-8 p-5 bg-surface-low/80 rounded-2xl border border-danger/20 w-full overflow-hidden text-left shadow-inner">
            <p className="text-[10px] font-mono text-danger/80 break-all leading-relaxed tracking-tight">
              Diagnostic_Err: {error.message}
            </p>
            {error.digest && (
              <p className="text-[10px] font-mono text-white/20 mt-2">
                Node_Id: {error.digest}
              </p>
            )}
          </div>
        )}
      </motion.div>

      <div className="absolute bottom-0 w-full">
        <GlobalFooter />
      </div>
    </div>
  );
}
