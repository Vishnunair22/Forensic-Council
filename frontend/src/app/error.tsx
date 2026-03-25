"use client";

import { useEffect } from "react";
import { AlertTriangle, RefreshCcw, Home } from "lucide-react";
import Link from "next/link";
import { motion } from "framer-motion";
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
        <div className="min-h-screen bg-background text-foreground flex flex-col items-center justify-center p-6 text-center relative overflow-hidden">
            {/* Background */}
            <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(239,68,68,0.08),transparent_60%)] pointer-events-none" />
            <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff04_1px,transparent_1px),linear-gradient(to_bottom,#ffffff04_1px,transparent_1px)] bg-[size:40px_40px] pointer-events-none" />

            <motion.div
                initial={{ opacity: 0, y: 24, scale: 0.94 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
                className="relative max-w-md w-full p-8 rounded-3xl
                  bg-white/[0.03] border border-red-500/25
                  shadow-[0_0_60px_rgba(239,68,68,0.08),inset_0_1px_0_rgba(255,255,255,0.06)]
                  backdrop-blur-2xl flex flex-col items-center z-10"
            >
                {/* Top shine */}
                <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-red-400/30 to-transparent rounded-t-3xl" />

                <div className="w-16 h-16 bg-red-500/10 border border-red-500/25 rounded-2xl
                  flex items-center justify-center mb-6
                  shadow-[0_0_30px_rgba(239,68,68,0.15)]">
                    <AlertTriangle className="w-8 h-8 text-red-400" />
                </div>

                <h1 className="text-2xl font-bold mb-3 text-foreground">Pipeline Interrupted</h1>

                <p className="text-slate-400 mb-8 text-sm leading-relaxed text-center">
                    An unexpected error occurred during the forensic analysis process.
                    The system has safely halted — no data has been lost.
                </p>

                <div className="w-full space-y-3">
                    <motion.button
                        onClick={() => reset()}
                        whileHover={{ scale: 1.02, y: -1 }}
                        whileTap={{ scale: 0.97 }}
                        className="btn btn-danger w-full py-3.5 rounded-xl"
                    >
                        <RefreshCcw className="w-4 h-4" />
                        Retry Analysis
                    </motion.button>

                    <Link href="/">
                        <motion.div
                            whileHover={{ scale: 1.02, y: -1 }}
                            whileTap={{ scale: 0.97 }}
                            className="btn btn-ghost w-full py-3.5 rounded-xl flex items-center justify-center gap-2 cursor-pointer"
                        >
                            <Home className="w-4 h-4" />
                            Return to Dashboard
                        </motion.div>
                    </Link>
                </div>

                {process.env.NODE_ENV === "development" && (
                    <div className="mt-6 p-4 bg-black/40 rounded-xl border border-red-500/20 w-full overflow-hidden text-left">
                        <p className="text-[10px] font-mono text-red-400 break-all leading-relaxed">{error.message}</p>
                        {error.digest && (
                            <p className="text-[10px] font-mono text-slate-600 mt-1">Digest: {error.digest}</p>
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
