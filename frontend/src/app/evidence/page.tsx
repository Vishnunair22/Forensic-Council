"use client";

import React from "react";
import { AnimatePresence } from "framer-motion";
import { PageTransition } from "@/components/ui/PageTransition";
import { useSound } from "@/hooks/useSound";
import { useInvestigation } from "@/hooks/useInvestigation";
import { LoadingOverlay } from "@/components/ui/LoadingOverlay";
import { ForensicProgressOverlay } from "@/components/ui/ForensicProgressOverlay";

import {
  FileUploadSection,
  AgentProgressDisplay,
  ErrorDisplay,
  HITLCheckpointModal,
} from "@/components/evidence";

export default function EvidencePage() {
  const { playSound } = useSound();

  const {
    file, setFile,
    isDragging, setIsDragging,
    validationError, setValidationError,
    isUploading,
    uploadPhaseText,
    showLoadingOverlay, setShowLoadingOverlay,
    arbiterLiveText,
    setAutoStartBlocking,
    phase,
    isSubmittingHITL,
    isNavigating,
    showArbiterOverlay,
    status,
    agentUpdates,
    validCompletedAgents,
    pipelineMessage,
    pipelineThinking,
    hitlCheckpoint,
    errorMessage,
    dismissCheckpoint,
    handleFile,
    triggerAnalysis,
    handleHITLDecision,
    handleAcceptAnalysis,
    handleDeepAnalysis,
    handleNewUpload,
    handleViewResults,
    resetSimulation,
    allAgentsDone,
    awaitingDecision,
    hasStartedAnalysis,
    showUploadForm,
    validAgentsData,
  } = useInvestigation(playSound);

  // Derive progress text for accessibility (NVDA)
  const runningAgentNames = Object.keys(agentUpdates)
    .map((id) => validAgentsData.find((a) => a.id === id)?.name)
    .filter((n): n is Exclude<typeof n, undefined> => n !== undefined);

  let progressText = uploadPhaseText || "Establishing secure forensic pipeline…";
  if (awaitingDecision) {
    progressText = "Initial analysis complete. Choose how to proceed.";
  } else if (phase === "deep" && (status === "complete" || allAgentsDone)) {
    progressText = "Deep analysis complete. All findings collected.";
  } else if (runningAgentNames.length > 0) {
    progressText = `${validCompletedAgents.length}/${validAgentsData.length} complete — ${runningAgentNames.length} agents scanning…`;
  }

  return (
    <div className="min-h-screen text-foreground p-6 pb-20 overflow-x-hidden relative font-sans selection:bg-cyan-500/30">
      {showLoadingOverlay && (
        <LoadingOverlay
          liveText={uploadPhaseText || "Initializing secure workspace..."}
        />
      )}

      {/* Council Overlay removed: Now integrated into AgentProgressDisplay Header */}

      <main className="max-w-[1400px] mx-auto relative z-10 w-full">
        <PageTransition>
          <>
            {showUploadForm && (
              <FileUploadSection
                key="upload-form"
                file={file}
                isDragging={isDragging}
                isUploading={isUploading}
                validationError={validationError}
                onFileSelect={handleFile}
                onFileDrop={handleFile}
                onDragEnter={() => setIsDragging(true)}
                onDragLeave={() => setIsDragging(false)}
                onUpload={triggerAnalysis}
                onClear={() => {
                  setFile(null);
                  setValidationError(null);
                }}
              />
            )}

            {hasStartedAnalysis && !showUploadForm && (
              <AgentProgressDisplay
                key="agent-progress"
                agentUpdates={agentUpdates}
                completedAgents={validCompletedAgents}
                progressText={progressText}
                allAgentsDone={allAgentsDone}
                phase={phase}
                awaitingDecision={awaitingDecision}
                pipelineStatus={status}
                pipelineMessage={pipelineMessage || pipelineThinking}
                onAcceptAnalysis={handleAcceptAnalysis}
                onDeepAnalysis={handleDeepAnalysis}
                onNewUpload={handleNewUpload}
                onViewResults={handleViewResults}
                playSound={playSound}
                isNavigating={isNavigating}
                mimeType={sessionStorage.getItem("forensic_mime_type") ?? undefined}
              />
            )}

            {(validationError || errorMessage) && !hasStartedAnalysis && !showUploadForm && (
              <div key="error-display" className="flex flex-col items-center justify-center min-h-[60vh]">
                <ErrorDisplay
                  message={validationError || errorMessage || "Unknown error"}
                  onDismiss={() => {
                    setValidationError(null);
                    resetSimulation();
                  }}
                  onRetry={() => file && triggerAnalysis(file)}
                  showRetry={!!file}
                />
              </div>
            )}

            {!showUploadForm && !hasStartedAnalysis && !showLoadingOverlay && !validationError && (
              <div className="flex flex-col items-center justify-center min-h-[50vh] gap-4 text-center px-6">
                <p className="text-sm text-foreground/55 max-w-md">
                  Initialising the forensic workspace...
                </p>
                <button
                  type="button"
                  onClick={() => {
                    setAutoStartBlocking(false);
                    setShowLoadingOverlay(false);
                    sessionStorage.removeItem("fc_show_loading");
                    sessionStorage.removeItem("forensic_auto_start");
                  }}
                  className="btn-pill-secondary px-6 py-2 text-xs"
                >
                  Reset loading & continue
                </button>
              </div>
            )}
          </>
        </PageTransition>
      </main>

      <AnimatePresence>
        {isNavigating && (
          <ForensicProgressOverlay
            variant="stream"
            title="Arbiter Deliberation"
            liveText={arbiterLiveText || "Synthesizing final verdict..."}
            telemetryLabel="Council Protocol"
            showElapsed
          />
        )}
      </AnimatePresence>

      <HITLCheckpointModal
        checkpoint={hitlCheckpoint}
        isOpen={!!hitlCheckpoint}
        isSubmitting={isSubmittingHITL}
        onDecision={handleHITLDecision}
        onDismiss={dismissCheckpoint}
      />

    </div>
  );
}
