"use client";

import { useEffect } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, RefreshCcw, Home } from "lucide-react";
import Link from "next/link";

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
    <html lang="en" data-scroll-behavior="smooth">
      <body>
        <div className="min-h-screen text-foreground flex flex-col items-center justify-center p-6 text-center relative overflow-hidden">
          <motion.div
            className="relative max-w-md w-full p-8 rounded-3xl overflow-hidden flex flex-col items-center z-10 border border-red-500/15 bg-white/[0.03]"
            style={{
              backdropFilter: "blur(24px)",
              boxShadow:
                "0 32px 80px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.04)",
            }}
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ duration: 0.4, ease: [0.34, 1.56, 0.64, 1] }}
          >
            <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-red-400/30 to-transparent rounded-t-3xl" />

            <motion.div
              className="w-16 h-16 bg-red-500/10 border border-red-500/25 rounded-2xl flex items-center justify-center mb-6 shadow-[0_0_30px_rgba(239,68,68,0.15)]"
              animate={{ scale: [1, 1.05, 1] }}
              transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
            >
              <AlertTriangle className="w-8 h-8 text-red-400" />
            </motion.div>

            <h1 className="text-2xl font-bold mb-3 text-foreground">
              Pipeline Interrupted
            </h1>

            <p className="text-slate-400 mb-8 text-sm leading-relaxed text-center">
              An unexpected error occurred during the forensic analysis process. The
              system has safely halted — no data has been lost.
            </p>

            <div className="w-full space-y-3">
              <motion.button
                onClick={() => reset()}
                className="w-full py-3.5 rounded-xl inline-flex items-center justify-center gap-2 font-bold text-white border border-cyan-400/30"
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
                <RefreshCcw className="w-4 h-4" />
                Retry Analysis
              </motion.button>

              <Link
                href="/"
                className="w-full py-3.5 rounded-xl inline-flex items-center justify-center gap-2 font-semibold text-white/80 bg-white/[0.04] border border-white/[0.09] hover:bg-cyan-500/[0.07] hover:border-cyan-500/28 hover:text-cyan-400 transition-colors"
              >
                <Home className="w-4 h-4" />
                Return to Dashboard
              </Link>
            </div>

            {process.env.NODE_ENV === "development" && (
              <div className="mt-6 p-4 bg-black/40 rounded-xl border border-red-500/20 w-full overflow-hidden text-left">
                <p className="text-[10px] font-mono text-red-400 break-all leading-relaxed">
                  {error.message}
                </p>
                {error.digest && (
                  <p className="text-[10px] font-mono text-slate-600 mt-1">
                    Digest: {error.digest}
                  </p>
                )}
              </div>
            )}
          </motion.div>
        </div>
      </body>
    </html>
  );
}
