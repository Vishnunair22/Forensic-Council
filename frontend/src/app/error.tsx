"use client";

import { useEffect } from "react";
import { AlertTriangle, RefreshCcw } from "lucide-react";
import Link from "next/link";
import { motion } from "framer-motion";

export default function GlobalError({
    error,
    reset,
}: {
    error: Error & { digest?: string };
    reset: () => void;
}) {
    useEffect(() => {
        // Log the error to an error reporting service
        console.error("Global app error:", error);
    }, [error]);

    return (
        <div className="min-h-screen bg-black text-white flex flex-col items-center justify-center p-6 text-center">
            <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-red-900/20 via-black to-black -z-50" />

            <motion.div
                initial={{ opacity: 0, y: 20, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                className="max-w-md w-full p-8 rounded-3xl bg-slate-900/50 border border-red-500/30 shadow-2xl shadow-red-500/10 backdrop-blur-xl flex flex-col items-center"
            >
                <div className="w-16 h-16 bg-red-500/10 text-red-500 rounded-2xl flex items-center justify-center mb-6">
                    <AlertTriangle className="w-8 h-8" />
                </div>

                <h1 className="text-2xl font-bold mb-4">Pipeline Interrupted</h1>

                <p className="text-slate-400 mb-8 text-sm leading-relaxed">
                    An unexpected anomaly occurred during the forensic analysis process. The system has safely halted to prevent data corruption. No data has been lost.
                </p>

                <div className="w-full space-y-3">
                    <button
                        onClick={() => reset()}
                        className="w-full py-4 bg-red-600 hover:bg-red-500 text-white rounded-xl font-bold transition-all flex items-center justify-center gap-2 group"
                    >
                        <RefreshCcw className="w-5 h-5 group-hover:-rotate-90 transition-transform duration-500" />
                        Reboot Analysis Module
                    </button>

                    <Link
                        href="/"
                        className="w-full py-4 border border-white/10 hover:bg-white/5 text-slate-300 rounded-xl font-semibold transition-all flex items-center justify-center text-center block"
                    >
                        Return to Dashboard
                    </Link>
                </div>

                {process.env.NODE_ENV === "development" && (
                    <div className="mt-8 p-4 bg-black/50 rounded-xl border border-red-500/20 w-full overflow-hidden text-left">
                        <p className="text-red-400 font-mono text-[10px] break-all">
                            {error.message}
                        </p>
                    </div>
                )}
            </motion.div>
        </div>
    );
}
