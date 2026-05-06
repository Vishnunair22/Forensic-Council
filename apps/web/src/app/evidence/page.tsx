"use client";

import { useState, useEffect } from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Shield, CheckCircle2, Cpu } from "lucide-react";
import { ForensicErrorModal } from "@/components/ui/ForensicErrorModal";

import { LoadingOverlay } from "@/components/ui/LoadingOverlay";
import { useInvestigation } from "@/hooks/useInvestigation";
import { useSound } from "@/hooks/useSound";
import { storage, sessionOnlyStorage } from "@/lib/storage";
import { __pendingFileStore } from "@/lib/pendingFileStore";
import { AgentProgressSkeleton } from "@/components/evidence/AgentProgressSkeleton";

const AgentProgressDisplay = dynamic(
  () => import("@/components/evidence/AgentProgressDisplay").then((mod) => mod.AgentProgressDisplay),
  { loading: () => <AgentProgressSkeleton /> },
);
const ArbiterDeliberationOverlay = dynamic(
  () => import("@/components/evidence/ArbiterDeliberationOverlay").then((mod) => mod.ArbiterDeliberationOverlay),
  { ssr: false },
);
const HITLCheckpointModal = dynamic(
  () => import("@/components/evidence/HITLCheckpointModal").then((mod) => mod.HITLCheckpointModal),
  { ssr: false },
);

export default function EvidenceUploadPage() {
  const router = useRouter();
  const { playSound } = useSound();
  const investigation = useInvestigation(playSound);

  useEffect(() => {
    document.body.style.overflow = "";
    // If no pending file and no session, ensure no stale state
    if (!__pendingFileStore.file && !storage.getItem("forensic_session_id")) {
      sessionOnlyStorage.removeItem("forensic_auto_start");
    }
    const onShow = (e: PageTransitionEvent) => { if (e.persisted) window.location.reload(); };
    window.addEventListener("pageshow", onShow);
    return () => window.removeEventListener("pageshow", onShow);
  }, []);

  const showAgentProgress = investigation.hasStartedAnalysis && !investigation.showUploadForm;

  return (
    <>
      {/* Overlays live OUTSIDE the opacity wrapper — fixed position must not
          inherit a parent opacity compositing context or they become invisible */}
      <ArbiterDeliberationOverlay 
        isVisible={investigation.arbiterDeliberating} 
        liveText={investigation.arbiterLiveText}
      />

      <AnimatePresence mode="wait">
        {investigation.showLoadingOverlay && !investigation.arbiterDeliberating && (
          <LoadingOverlay
            variant="full"
            liveText={investigation.uploadPhaseText || investigation.pipelineMessage || "Initializing Workspace..."}
            dispatchedCount={Math.min(Object.keys(investigation.agentUpdates).filter(k => k !== "Arbiter").length, 5)}
            totalAgents={5}
          />
        )}
      </AnimatePresence>

      <div className={`relative min-h-screen px-6 py-32 transition-opacity duration-300 ${investigation.showLoadingOverlay ? "opacity-0" : "opacity-100"}`}>
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
            mimeType={investigation.file?.type || storage.getItem("forensic_mime_type") || undefined}
            playSound={playSound}
            revealQueue={investigation.revealQueue}
            arbiterDeliberating={investigation.arbiterDeliberating}
            arbiterStatus={investigation.arbiterStatus}
            arbiterThinking={investigation.arbiterThinking}
            hasStartedAnalysis={investigation.hasStartedAnalysis}
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
              initial={{ opacity: 0, y: 20 }}
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
                onClick={() => router.push("/")}
                className="btn-horizon-primary mt-4"
              >
                Return Home
              </button>
            </motion.div>
          </section>
        )}
      )}
    </div>
    </>
  );
}
