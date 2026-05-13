"use client";

import { useEffect, Suspense } from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { Shield } from "lucide-react";
import { ForensicErrorModal } from "@/components/ui/ForensicErrorModal";

import { LoadingOverlay } from "@/components/ui/LoadingOverlay";
import { useInvestigation } from "@/hooks/useInvestigation";
import { useSound } from "@/hooks/useSound";
import { storage, sessionOnlyStorage } from "@/lib/storage";
import { __pendingFileStore } from "@/lib/pendingFileStore";
import { AgentProgressSkeleton } from "@/components/evidence/AgentProgressSkeleton";
import { resetActiveInvestigation } from "@/lib/appReset";

const AgentProgressDisplay = dynamic(
  () => import("@/components/evidence/AgentProgressDisplay").then((mod) => mod.AgentProgressDisplay),
);
const ArbiterDeliberationOverlay = dynamic(
  () => import("@/components/evidence/ArbiterDeliberationOverlay").then((mod) => mod.ArbiterDeliberationOverlay),
  { ssr: false },
);
const HITLCheckpointModal = dynamic(
  () => import("@/components/evidence/HITLCheckpointModal").then((mod) => mod.HITLCheckpointModal),
  { ssr: false },
);

export function EvidenceUploadClient() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { playSound } = useSound();
  const prefersReducedMotion = useReducedMotion();
  const investigation = useInvestigation(playSound);

  useEffect(() => {
    document.body.style.overflow = "";
    if (!__pendingFileStore.file && !storage.getItem("forensic_session_id")) {
      sessionOnlyStorage.removeItem("forensic_auto_start");
    }
    // On bfcache restore with no session, navigate home rather than reloading
    // to avoid potential infinite reload loops in some browsers.
    const onShow = (e: PageTransitionEvent) => {
      if (e.persisted && !storage.getItem("forensic_session_id")) {
        router.replace("/");
      }
    };
    window.addEventListener("pageshow", onShow);
    return () => window.removeEventListener("pageshow", onShow);
  }, [router]);

  useEffect(() => {
    const hasPendingFile = !!__pendingFileStore.file;
    const hasSessionId = !!storage.getItem("forensic_session_id");
    const isRunning = investigation.status === "analyzing" || investigation.status === "initiating" || investigation.status === "processing";

    const shouldWarn = hasPendingFile && !hasSessionId && isRunning;

    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (shouldWarn) {
        e.preventDefault();
        return "";
      }
    };

    if (shouldWarn) {
      window.addEventListener("beforeunload", onBeforeUnload);
    }

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
            liveText={investigation.uploadPhaseText || investigation.pipelineMessage || "Initializing Workspace..."}
            dispatchedCount={Math.min(Object.keys(investigation.agentUpdates).filter(k => k !== "Arbiter").length, 5)}
            playSound={playSound}
          />
        )}
      </AnimatePresence>

      <div className="relative min-h-screen px-4 sm:px-6 py-24 sm:py-32">
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

        {showAgentProgress ? (
          <>
          <Suspense fallback={<AgentProgressSkeleton mimeType={investigation.mimeType} />}>
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
            />
          </Suspense>

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
              initial={prefersReducedMotion ? false : { opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="text-center space-y-6"
            >
              <div className="flex items-center justify-center gap-2 opacity-40 mb-2">
                <Shield className="w-4 h-4 text-primary" />
                <span className="text-[10px] uppercase tracking-[0.3em] font-mono font-black">
                  Intake Protocol
                </span>
              </div>
              <h1 className="text-4xl font-extrabold tracking-tighter text-white">
                No Evidence Queued
              </h1>
              <p className="text-white/40 text-base max-w-sm mx-auto leading-relaxed">
                Return to the home page to upload evidence and begin a new investigation.
              </p>
              <button
                onClick={() => {
                  resetActiveInvestigation(queryClient);
                  router.push("/");
                }}
                className="btn-horizon-primary mt-4"
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