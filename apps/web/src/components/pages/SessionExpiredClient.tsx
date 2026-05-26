"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { useQueryClient } from "@tanstack/react-query";
import { GlassPanel } from "@/components/ui/GlassPanel";
import { ShieldAlert, ArrowLeft, RefreshCw, Cpu } from "lucide-react";
import { sessionOnlyStorage } from "@/lib/storage";
import { STORAGE_KEYS } from "@/lib/storageKeys";
import { resetActiveInvestigation } from "@/lib/appReset";

export function SessionExpiredClient() {
  const router = useRouter();
  const queryClient = useQueryClient();

  useEffect(() => {
    resetActiveInvestigation(queryClient);
  }, [queryClient]);

  return (
    <div className="relative min-h-[calc(100vh-4rem)] flex items-center justify-center px-6 py-16 overflow-hidden">
      {/* Background Decorative Elements */}
      <div className="absolute top-0 left-0 w-full h-full pointer-events-none overflow-hidden -z-10">
        <div className="absolute top-[20%] left-[-10%] w-[40%] h-[40%] bg-red-500/5 blur-[120px] rounded-full" />
      </div>

      <div className="w-full max-w-md mx-auto relative z-10 text-center space-y-8">
        <motion.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.16 }}
          className="space-y-4"
        >
          <div className="flex items-center justify-center gap-2 fc-text-muted">
            <ShieldAlert className="w-4 h-4 text-red-500" aria-hidden="true" />
            <span className="fc-eyebrow">
              Security Boundary
            </span>
          </div>
          <h1
            aria-label="Session expired"
            className="text-3xl md:text-4xl font-extrabold tracking-tighter leading-none text-white"
          >
            Session Expired
          </h1>
          <p className="text-base fc-text-secondary font-medium leading-relaxed">
            Your session has expired or is no longer valid. Please start a new analysis to continue.
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.16, delay: 0.08 }}
        >
          <GlassPanel className="p-10 rounded-3xl border border-border-subtle space-y-8 relative overflow-hidden">
             <div className="absolute top-4 right-4 opacity-[0.03]" aria-hidden="true">
                <Cpu className="w-12 h-12" />
             </div>

            <p className="text-sm fc-text-muted leading-relaxed font-medium">
              Return to the hub to start a new forensic analysis.
            </p>

            <div className="space-y-3">
              <button
                type="button"
                onClick={() => {
                  // WORKFLOW_TRACE: session-expired -> Return to Hub MUST dispatch
                  // fc:reset-home so HeroAuthActions clears modal/file state.
                  if (window.location.pathname === "/") {
                    window.dispatchEvent(new Event("fc:reset-home"));
                  } else {
                    router.push("/");
                  }
                }}
                className="w-full fc-btn-primary flex items-center justify-center gap-2"
                data-testid="session-expired-home-cta"
                aria-label="Return to Hub"
              >
                <ArrowLeft className="w-4 h-4" />
                Return to Hub
              </button>

              <button
                type="button"
                onClick={() => {
                  sessionOnlyStorage.setItem(STORAGE_KEYS.FC_OPEN_UPLOAD_ONCE, "1");
                  if (window.location.pathname === "/") {
                    window.dispatchEvent(new Event("fc:open-upload"));
                  } else {
                    router.push("/");
                  }
                }}
                className="w-full fc-btn-secondary flex items-center justify-center gap-2"
                data-testid="session-expired-retry-cta"
                aria-label="New Intake — start a new forensic analysis"
              >
                <RefreshCw className="w-4 h-4" />
                New Analysis
              </button>
            </div>
          </GlassPanel>
        </motion.div>

        {/* Micro-accent */}
        <div className="flex justify-center">
           <div className="h-[1px] w-12 bg-white/20" />
           <div className="mx-4 fc-eyebrow fc-text-muted">Security Boundary</div>
           <div className="h-[1px] w-12 bg-white/20" />
        </div>
      </div>
    </div>
  );
}
