"use client";

import { useEffect } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, RefreshCcw, Home } from "lucide-react";
import Link from "next/link";
import { GlobalFooter } from "@/components/ui/GlobalFooter";

export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") {
      console.error("Global app error:", error);
    }
  }, [error]);

  return (
    <div className="min-h-screen text-foreground flex flex-col items-center justify-center p-6 text-center relative overflow-hidden bg-background">
      <motion.div
        className="relative max-w-md w-full p-10 rounded-3xl overflow-hidden flex flex-col items-center z-10 fc-surface-elevated border-danger/20"
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.16, ease: "easeOut" }}
      >
        <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-transparent via-danger/40 to-transparent" />

        <div className="w-20 h-20 bg-danger/10 border border-danger/30 rounded-2xl flex items-center justify-center mb-8">
          <AlertTriangle className="w-10 h-10 text-danger" />
        </div>

        <h1 className="text-3xl font-extrabold mb-4 text-white tracking-tighter">
          System <span className="text-danger">Interrupted</span>
        </h1>

        <p className="fc-text-muted mb-8 text-sm leading-relaxed text-center">
          An unexpected error occurred during the forensic analysis process. The
          system has safely halted — no data has been lost.
        </p>

        <div className="w-full space-y-4">
          <motion.button
            onClick={() => reset()}
            className="fc-btn-primary w-full py-4 tracking-wide"
            whileTap={{ scale: 0.98 }}
          >
            <RefreshCcw className="w-4 h-4" />
            Retry Analysis
          </motion.button>

          <Link
            href="/"
            className="fc-btn-secondary w-full py-4 tracking-wide"
          >
            <Home className="w-4 h-4" />
            Return to Hub
          </Link>
        </div>

        {process.env.NODE_ENV === "development" && (
          <div className="mt-8 p-5 rounded-2xl border border-danger/20 w-full overflow-hidden text-left shadow-inner">
            <p className="text-xs font-mono text-danger/80 break-all leading-relaxed tracking-tight">
              Diagnostic_Err: {error.message}
            </p>
            {error.digest && (
              <p className="text-xs font-mono fc-text-faint mt-2">
                ID: {error.digest}
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
