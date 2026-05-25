"use client";

import { Component, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { motion, useReducedMotion } from "framer-motion";
import { Shield } from "lucide-react";
import { ForensicErrorModal } from "@/components/ui/ForensicErrorModal";

import { useInvestigation } from "@/hooks/useInvestigation";
import { useSound } from "@/hooks/useSound";
import { storage, sessionOnlyStorage } from "@/lib/storage";
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

class AgentProgressErrorBoundary extends Component<
  { children: React.ReactNode; onError?: (error: Error) => void },
  { hasError: boolean }
> {
  constructor(props: { children: React.ReactNode; onError?: (error: Error) => void }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): { hasError: boolean } {
    return { hasError: true };
  }

  componentDidCatch(error: Error) {
    console.error("[AgentProgressDisplay Error]:", error);
    this.props.onError?.(error);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="w-full max-w-2xl mx-auto text-center p-8">
          <p className="text-danger mb-4">Analysis display encountered an error.</p>
          <button
            onClick={() => window.location.reload()}
            className="fc-btn-primary"
          >
            Reload Page
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export function EvidenceUploadClient() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { playSound } = useSound();
  const prefersReducedMotion = useReducedMotion();
  const investigation = useInvestigation(playSound);

  const [isMounted, setIsMounted] = useState(false);
  const [handoffPending, setHandoffPending] = useState(() => {
    if (typeof window === "undefined") return false;
    const autoStart = sessionOnlyStorage.getItem(STORAGE_KEYS.AUTO_START) === "true";
    const showLoading = sessionOnlyStorage.getItem(STORAGE_KEYS.FC_SHOW_LOADING) === "true";
    return autoStart || showLoading;
  });

  useEffect(() => {
    const frame = requestAnimationFrame(() => setIsMounted(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    const handleReset = () => setHandoffPending(false);
    window.addEventListener("fc:reset-home", handleReset);
    return () => window.removeEventListener("fc:reset-home", handleReset);
  }, []);

  useEffect(() => {
    if (handoffPending) {
      const timer = setTimeout(() => {
        setHandoffPending(false);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [handoffPending]);

  useEffect(() => {
    document.body.style.overflow = "";
    window.scrollTo({ top: 0, behavior: "instant" });
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

  // Loading flag lifecycle is managed by GlobalLoadingOverlay (root layout) and
  // useInvestigation's sync effect. GlobalLoadingOverlay reads FC_SHOW_LOADING
  // from sessionStorage and dismisses itself based on pathname changes and a
  // safety timer. useInvestigation sets/clears FC_SHOW_LOADING as the analysis
  // progresses. Do NOT add a cleanup here that strips FC_SHOW_LOADING — in Strict
  // Mode development this cleanup fires on the simulated unmount, dispatching
  // fc_storage_update events that cause GlobalLoadingOverlay to hide prematurely,
  // creating the "loading loop" flicker.

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
        e.returnValue = ""; // Modern browser compliance
        return ""; // Legacy fallback
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

        {showAgentProgress || investigation.handoffRecovering || handoffPending ? (
          isMounted && (
            <motion.div
              initial={{ opacity: 0, scale: 1.02 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.5, ease: "easeOut", delay: 0.1 }}
              className="w-full max-w-7xl mx-auto"
            >
               <AgentProgressErrorBoundary>
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
                  overlayVisible={investigation.showLoadingOverlay}
                />
               </AgentProgressErrorBoundary>

              <HITLCheckpointModal
                checkpoint={investigation.hitlCheckpoint}
                isOpen={!!investigation.hitlCheckpoint}
                isSubmitting={investigation.isSubmittingHITL}
                onDecision={investigation.handleHITLDecision}
                onDismiss={investigation.dismissCheckpoint}
              />
            </motion.div>
          )
        ) : (
          isMounted && (
            <section className="relative flex min-h-[calc(100vh-16rem)] items-center justify-center">
              <motion.div
                initial={prefersReducedMotion ? false : { opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.16 }}
                className="text-center space-y-6"
              >
                <div className="flex items-center justify-center gap-2 mb-2">
                  <Shield className="w-4 h-4 fc-text-muted" />
                  <span className="fc-eyebrow fc-text-muted">
                    Intake Protocol
                  </span>
                </div>
                <h1 className="text-4xl font-heading font-black tracking-tight fc-text-primary">
                  No Evidence Queued
                </h1>
                <p className="fc-text-secondary text-base max-w-sm mx-auto leading-relaxed">
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
          )
        )}
      </div>
    </>
  );
}
