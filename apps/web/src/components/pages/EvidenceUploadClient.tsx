"use client";

import { useEffect } from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { Shield } from "lucide-react";
import { ForensicErrorModal } from "@/components/ui/ForensicErrorModal";

import { LoadingOverlay } from "@/components/ui/LoadingOverlay";
import { useInvestigation } from "@/hooks/useInvestigation";
import { useSound } from "@/hooks/useSound";
import { storage } from "@/lib/storage";
import { STORAGE_KEYS } from "@/lib/storageKeys";
import { __pendingFileStore } from "@/lib/pendingFileStore";
import { resetActiveInvestigation } from "@/lib/appReset";
import { ArbiterDeliberationOverlay } from "@/components/evidence/ArbiterDeliberationOverlay";
import { HITLCheckpointModal } from "@/components/evidence/HITLCheckpointModal";

// F-H-5: dynamic() loading prop handles chunk-fetch fallback. A React
// Suspense wrapper around `next/dynamic` lazy components is dead code
// because `next/dynamic` does not suspend by default.
const AgentProgressDisplay = dynamic(
  () => import("@/components/evidence/AgentProgressDisplay").then((mod) => mod.AgentProgressDisplay),
  { loading: () => null },
);

export function EvidenceUploadClient() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { playSound } = useSound();
  const prefersReducedMotion = useReducedMotion();
  const investigation = useInvestigation(playSound);

  useEffect(() => {
    document.body.style.overflow = "";
    // On bfcache restore with no session, navigate home rather than reloading
    // to avoid potential infinite reload loops in some browsers.
    const onShow = (e: PageTransitionEvent) => {
      if (e.persisted && !storage.getItem(STORAGE_KEYS.SESSION_ID)) {
        router.replace("/");
      }
    };
    window.addEventListener("pageshow", onShow);
    return () => window.removeEventListener("pageshow", onShow);
  }, [router]);

  useEffect(() => {
    // F-C-3: compute shouldWarn INSIDE the handler so the latest pending-file
    // and session state are read at unload time. The previous closure captured
    // stale values from effect-run time.
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      const hasPendingFile = !!__pendingFileStore.file;
      const hasSessionId = !!storage.getItem(STORAGE_KEYS.SESSION_ID);
      const s = investigation.status;
      const isRunning = s === "analyzing" || s === "initiating" || s === "processing";
      if (hasPendingFile && !hasSessionId && isRunning) {
        e.preventDefault();
        return "";
      }
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
    };
  }, [investigation.status]);

  const showAgentProgress = investigation.hasStartedAnalysis;

  return (
    <>
      {/* Overlays live OUTSIDE the opacity wrapper — fixed position must not
          inherit a parent opacity compositing context or they become invisible */}
      <ArbiterDeliberationOverlay 
        isVisible={investigation.arbiterDeliberating} 
        liveText={investigation.arbiterLiveText}
      />

      <AnimatePresence initial={false}>
        {investigation.showLoadingOverlay && !investigation.arbiterDeliberating && (
          <LoadingOverlay
            liveText={investigation.uploadPhaseText || investigation.pipelineMessage || "Initializing workspace"}
            dispatchedCount={Math.min(Object.keys(investigation.agentUpdates).filter(k => k !== "Arbiter").length, 5)}
            playSound={playSound}
          />
        )}
      </AnimatePresence>

      <div className="relative min-h-screen px-4 sm:px-6 py-10 sm:py-14">
        {investigation.wsConnectionError && !investigation.isReconnecting && (
          <ForensicErrorModal
            isVisible
            isTransient={investigation.isReconnecting}
            title="Stream Connection Failed"
            message={investigation.wsConnectionError}
            errorCode="0xFC_WS_LOST"
            onRetry={investigation.retryWsConnection}
            onHome={investigation.handleNewUpload}
          />
        )}

        {showAgentProgress || investigation.handoffRecovering ? (
          <>
             <AgentProgressDisplay
               agentUpdates={investigation.agentUpdates}
               completedAgents={investigation.validCompletedAgents}
               progressText={investigation.pipelineThinking}
               allAgentsDone={investigation.allAgentsDone}
               phase={investigation.phase}
               awaitingDecision={investigation.awaitingDecision}
               pipelineStatus={investigation.status}
               pipelineMessage={investigation.pipelineMessage}
               onNewUpload={investigation.handleNewUpload}
               onViewResults={investigation.handleViewResults}
               onAcceptAnalysis={investigation.handleAcceptAnalysis}
               onRunDeepAnalysis={investigation.handleDeepAnalysis}
               isNavigating={investigation.isNavigating}
               mimeType={investigation.mimeType || undefined}
               playSound={playSound}
               revealQueue={investigation.revealQueue}
               arbiterDeliberating={investigation.arbiterDeliberating}
               arbiterStatus={investigation.arbiterStatus}
               arbiterThinking={investigation.arbiterThinking}
               hasStartedAnalysis={investigation.hasStartedAnalysis}
               overlayVisible={investigation.showLoadingOverlay}
             />

            <HITLCheckpointModal
              checkpoint={investigation.hitlCheckpoint}
              isOpen={!!investigation.hitlCheckpoint}
              isSubmitting={investigation.isSubmittingHITL}
              onDecision={investigation.handleHITLDecision}
              onDismiss={investigation.dismissCheckpoint}
            />
          </>
        ) : (

          <section className="relative flex min-h-[calc(100vh-16rem)] items-center justify-center">
            <motion.div
              initial={prefersReducedMotion ? false : { opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.16 }}
              className="text-center space-y-6"
            >
              <div className="flex items-center justify-center gap-2 mb-2">
                <Shield className="w-4 h-4 fc-text-faint" />
                <span className="fc-eyebrow fc-text-faint">
                  Intake Protocol
                </span>
              </div>
              <h1 className="text-4xl font-heading font-black tracking-tight fc-text-primary">
                No Evidence Queued
              </h1>
              <p className="fc-text-faint text-base max-w-sm mx-auto leading-relaxed">
                Return to the home page to upload evidence and begin a new investigation.
              </p>
              <button
                onClick={() => {
                  resetActiveInvestigation(queryClient);
                  router.push("/");
                }}
                className="fc-btn-primary mt-4"
              >
                Return Home
              </button>
            </motion.div>
          </section>
        )}
      </div>
    </>
  );
}
