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
import { loadingOverlayController } from "@/lib/upload/loadingOverlayController";
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
            type="button"
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

  useEffect(() => {
    const frame = requestAnimationFrame(() => setIsMounted(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    document.body.style.overflow = "";
    window.scrollTo({ top: 0, behavior: "instant" });
    // On bfcache restore with no session, navigate home rather than reloading
    // to avoid potential infinite reload loops in some browsers.
    const onShow = (e: PageTransitionEvent) => {
      if (e.persisted) {
        // Defer check by one tick so sessionStorage writes from triggerAnalysis can complete
        setTimeout(() => {
          if (!storage.getItem(STORAGE_KEYS.SESSION_ID) && 
              sessionOnlyStorage.getItem(STORAGE_KEYS.FC_HANDOFF_FIRED) !== "1") {
            loadingOverlayController.forceDismiss();
            router.replace("/");
          }
        }, 200);
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
    const isUploadInProgress = () => {
      const hasPendingFile = !!__pendingFileStore.file;
      const hasSessionId = !!storage.getItem(STORAGE_KEYS.SESSION_ID);
      const s = investigation.status;
      const isRunning = s === "analyzing" || s === "initiating" || s === "processing";
      return hasPendingFile && !hasSessionId && isRunning;
    };

    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (isUploadInProgress()) {
        e.preventDefault();
        e.returnValue = ""; // Modern browser compliance
        return ""; // Legacy fallback
      }
    };

    // Covers browser back/forward (including iOS Safari which skips beforeunload on route changes)
    const onPopState = () => {
      if (isUploadInProgress()) {
        const confirmed = window.confirm(
          "An upload is in progress. Leaving this page will cancel it. Continue?"
        );
        if (!confirmed) {
          window.history.pushState(null, "", window.location.href);
        }
      }
    };

    window.addEventListener("beforeunload", onBeforeUnload);
    window.addEventListener("popstate", onPopState);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
      window.removeEventListener("popstate", onPopState);
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
            isTransient={false}
            title="Stream Connection Failed"
            message={investigation.wsConnectionError}
            errorCode="0xFC_WS_LOST"
            onRetry={investigation.retryWsConnection}
            onHome={investigation.handleNewUpload}
          />
        )}

        {showAgentProgress || investigation.handoffRecovering ? (
          <motion.div
              initial={prefersReducedMotion ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
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
                  capabilities={investigation.capabilities}
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
        ) : isMounted ? (
            <section className="relative flex min-h-[calc(100vh-16rem)] items-center justify-center">
              <motion.div
                initial={prefersReducedMotion ? false : { opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
                className="text-center space-y-6"
              >
                <div className="flex items-center justify-center gap-2 mb-2">
                  <Shield className="w-4 h-4 fc-text-muted" />
                  <span className="fc-eyebrow fc-text-muted">
                    Intake Protocol
                  </span>
                </div>
                <h1 className="text-4xl font-heading font-extrabold tracking-tight fc-text-primary">
                  No Evidence Queued
                </h1>
                <p className="fc-text-secondary text-base max-w-sm mx-auto leading-relaxed">
                  Return to the home page to upload evidence and begin a new investigation.
                </p>
                <button
                  type="button"
                  onClick={async () => {
                    await resetActiveInvestigation(queryClient);
                    router.push("/");
                  }}
                  className="fc-btn-primary mt-4"
                >
                  Return Home
                </button>
              </motion.div>
            </section>
        ) : (
          /* Skeleton shown during the requestAnimationFrame mount tick —
             prevents the blank flash that isMounted && (...) previously caused */
          <section className="relative flex min-h-[calc(100vh-16rem)] items-center justify-center">
            <div className="text-center space-y-4 w-64" aria-hidden="true">
              <div className="fc-skeleton h-10 w-48 mx-auto rounded-xl" />
              <div className="fc-skeleton h-4 w-full rounded" />
              <div className="fc-skeleton h-4 w-3/4 mx-auto rounded" />
            </div>
          </section>
        )}
      </div>
    </>
  );
}
