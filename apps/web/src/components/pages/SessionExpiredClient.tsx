"use client";

import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { GlassPanel } from "@/components/ui/GlassPanel";
import { ShieldAlert, ArrowLeft, RefreshCw, Cpu } from "lucide-react";
import { sessionOnlyStorage } from "@/lib/storage";

export function SessionExpiredClient() {
  const router = useRouter();

  return (
    <main className="relative min-h-screen flex items-center justify-center px-6 py-32 overflow-hidden">
      {/* Background Decorative Elements */}
      <div className="absolute top-0 left-0 w-full h-full pointer-events-none overflow-hidden -z-10">
        <div className="absolute top-[20%] left-[-10%] w-[40%] h-[40%] bg-red-500/5 blur-[120px] rounded-full" />
      </div>

      <div className="w-full max-w-md mx-auto relative z-10 text-center space-y-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="space-y-4"
        >
          <div className="flex items-center justify-center gap-2 fc-text-faint">
            <ShieldAlert className="w-4 h-4 text-red-500" />
            <span className="fc-eyebrow">
              Security Boundary
            </span>
          </div>
          <h1
            aria-label="Session expired"
            className="text-3xl md:text-4xl font-extrabold tracking-tighter leading-none text-white"
          >
            Session De-synchronized
          </h1>
          <p className="text-base fc-text-secondary font-medium leading-relaxed">
            The investigative payload session has either concluded, expired, or lacked appropriate validation signatures.
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.1 }}
        >
          <GlassPanel className="p-10 rounded-3xl border border-border-subtle space-y-8 relative overflow-hidden">
             <div className="absolute top-4 right-4 opacity-[0.03]">
                <Cpu className="w-12 h-12" />
             </div>

            <p className="text-sm text-white/60 leading-relaxed font-medium">
              Authenticate again to continue forensic analysis. Return to the central hub to start a new digital forensic ledger sequence.
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
                className="w-full py-4 rounded-full bg-primary text-background shadow-[0_0_30px_rgba(var(--color-primary-rgb),0.2)] text-sm font-black transition-all flex items-center justify-center gap-3 group"
                data-testid="session-expired-home-cta"
                aria-label="Return to dashboard"
              >
                <ArrowLeft className="w-4 h-4" />
                Return to Hub
              </button>
              
              <button
                type="button"
                onClick={() => {
                  sessionOnlyStorage.setItem("fc_open_upload_once", "1");
                  if (window.location.pathname === "/") {
                    window.dispatchEvent(new Event("fc:open-upload"));
                  } else {
                    router.push("/");
                  }
                }}
                className="w-full py-4 rounded-full bg-white/5 border border-white/10 text-white hover:bg-white/10 text-sm font-black transition-all flex items-center justify-center gap-3"
                data-testid="session-expired-retry-cta"
              >
                <RefreshCw className="w-4 h-4 opacity-60" />
                New Intake
              </button>
            </div>
          </GlassPanel>
        </motion.div>

        {/* Micro-accent */}
        <div className="flex justify-center">
           <div className="h-[1px] w-12 bg-white/20" />
           <div className="mx-4 fc-eyebrow fc-text-faint">System Halt</div>
           <div className="h-[1px] w-12 bg-white/20" />
        </div>
      </div>
    </main>
  );
}
