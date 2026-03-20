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
        <div className="min-h-screen bg-[#030308] text-white flex flex-col items-center justify-center p-6 text-center relative overflow-hidden">
            <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(245,158,11,0.07),transparent_60%)] pointer-events-none" />
            <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff03_1px,transparent_1px),linear-gradient(to_bottom,#ffffff03_1px,transparent_1px)] bg-[size:40px_40px] pointer-events-none" />

            <motion.div
                initial={{ opacity: 0, y: 24, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: 0.4, ease: "easeOut" }}
                className="glass-modal max-w-md w-full p-8 rounded-3xl flex flex-col items-center border-amber-500/20"
                style={{ borderColor: "rgba(245,158,11,0.18)" }}
            >
                {/* Amber tint top edge */}
                <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-amber-400/40 to-transparent rounded-t-3xl pointer-events-none" />

                <div className="w-16 h-16 bg-amber-500/10 border border-amber-500/25 text-amber-400 rounded-2xl flex items-center justify-center mb-6 shadow-[0_0_28px_rgba(245,158,11,0.15)]">
                    <ShieldX className="w-8 h-8" aria-hidden="true" />
                </div>

                <h1 className="text-2xl font-bold mb-3">Session Expired</h1>

                <p className="text-slate-400 mb-8 text-sm leading-relaxed text-center">
                    Your investigator session has expired or is no longer valid.
                    Please return to the dashboard and authenticate again to
                    continue forensic analysis.
                </p>

                <button
                    onClick={handleReturn}
                    className="btn w-full py-4 rounded-xl font-bold"
                    style={{
                      background: "linear-gradient(135deg, #d97706 0%, #b45309 100%)",
                      color: "white",
                      border: "1px solid rgba(245,158,11,0.4)",
                      boxShadow: "0 0 24px rgba(245,158,11,0.20)",
                    }}
                >
                    <LogIn className="w-5 h-5" aria-hidden="true" />
                    Return to Dashboard
                </button>
            </motion.div>
        </div>
    );
}
