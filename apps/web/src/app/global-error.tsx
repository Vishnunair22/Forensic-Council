"use client";

import { useEffect } from "react";
import { AlertTriangle, RefreshCcw, Home } from "lucide-react";
import Link from "next/link";
import "./globals.css";

export default function GlobalError({
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
    <html lang="en">
      <body className="bg-surface-0 min-h-screen fc-text-primary flex flex-col items-center justify-center p-6 text-center relative overflow-hidden">
        <div className="min-h-screen flex flex-col items-center justify-center w-full">
          <div className="fc-surface relative max-w-md w-full p-8 rounded-3xl overflow-hidden flex flex-col items-center z-10">
            <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-transparent via-danger/40 to-transparent" />

            <div className="w-16 h-16 rounded-2xl bg-danger/10 border border-danger/25 flex items-center justify-center mb-6">
              <AlertTriangle className="w-8 h-8 fc-text-danger" />
            </div>

            <h1 className="text-2xl font-bold mb-3 fc-text-primary">
              Pipeline Interrupted
            </h1>

            <p className="fc-text-muted mb-8 text-sm leading-relaxed text-center">
              An unexpected error occurred during the forensic analysis process. The
              system has safely halted — no data has been lost.
            </p>

            <div className="w-full space-y-3">
              <button
                onClick={() => reset()}
                className="fc-btn-primary w-full"
              >
                <RefreshCcw className="w-4 h-4" />
                Retry Analysis
              </button>

              <Link href="/" className="fc-btn-secondary w-full">
                <Home className="w-4 h-4" />
                Return To Home
              </Link>
            </div>

            {process.env.NODE_ENV === "development" && (
              <div className="mt-6 p-4 fc-surface-quiet rounded-xl border border-red-500/20 w-full overflow-hidden text-left">
                <p className="text-xs font-mono fc-text-danger break-all leading-relaxed">
                  {error.message}
                </p>
                {error.digest && (
                  <p className="text-xs font-mono fc-text-faint mt-1">
                    Digest: {error.digest}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      </body>
    </html>
  );
}
