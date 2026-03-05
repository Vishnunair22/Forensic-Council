"use client";

import { useEffect } from "react";
import { motion } from "framer-motion";
import { ShieldX, LogIn } from "lucide-react";
import { clearAuthToken } from "@/lib/api";
import { useRouter } from "next/navigation";

/**
 * Session Expired Page
 *
 * Shown when the API returns 401 and auto-reauth fails, or when
 * the user navigates to a protected page with an expired/missing token.
 * Clears the stale token and redirects to the login flow on the
 * landing page.
 */
export default function SessionExpiredPage() {
    const router = useRouter();

    useEffect(() => {
        // Clear any stale token immediately on mount
        clearAuthToken();
    }, []);

    const handleReturn = () => {
        clearAuthToken();
        router.push("/");
    };

    return (
        <div className="min-h-screen bg-black text-white flex flex-col items-center justify-center p-6 text-center">
            <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-amber-900/15 via-black to-black -z-50" />

            <motion.div
                initial={{ opacity: 0, y: 24, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: 0.4, ease: "easeOut" }}
                className="max-w-md w-full p-8 rounded-3xl bg-slate-900/60 border border-amber-500/25 shadow-2xl shadow-amber-500/10 backdrop-blur-xl flex flex-col items-center"
            >
                <div className="w-16 h-16 bg-amber-500/10 text-amber-400 rounded-2xl flex items-center justify-center mb-6">
                    <ShieldX className="w-8 h-8" />
                </div>

                <h1 className="text-2xl font-bold mb-3">Session Expired</h1>

                <p className="text-slate-400 mb-8 text-sm leading-relaxed">
                    Your investigator session has expired or is no longer valid.
                    Please return to the dashboard and authenticate again to
                    continue forensic analysis.
                </p>

                <button
                    onClick={handleReturn}
                    className="w-full py-4 bg-amber-600 hover:bg-amber-500 text-white rounded-xl font-bold transition-all flex items-center justify-center gap-2 group"
                >
                    <LogIn className="w-5 h-5" />
                    Return to Dashboard
                </button>
            </motion.div>
        </div>
    );
}
