"use client";

import React from "react";
import { AnimatePresence } from "framer-motion";
import { PageTransition } from "@/components/ui/PageTransition";
import { useSound } from "@/hooks/useSound";
import { useInvestigation } from "@/hooks/useInvestigation";
import { AnalysisProgressOverlay } from "@/components/evidence/AnalysisProgressOverlay";

import {
  FileUploadSection,
  AgentProgressDisplay,
  HITLCheckpointModal,
} from "@/components/evidence";
import { ForensicErrorModal } from "@/components/ui/ForensicErrorModal";
import { sessionOnlyStorage, storage } from "@/lib/storage";

const FORENSIC_MIME_TYPE_KEY = "forensic_mime_type";
const FC_SHOW_LOADING_KEY = "fc_show_loading";
const FORENSIC_AUTO_START_KEY = "forensic_auto_start";

export default function EvidencePage() {
  const { playSound } = useSound();

  const {
    file, setFile,
    isDragging, setIsDragging,
    validationError, setValidationError,
    isUploading,
    uploadPhaseText,
    showLoadingOverlay, setShowLoadingOverlay,
    setAutoStartBlocking,
    phase,
    isSubmittingHITL,
    isNavigating,
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
    retryWsConnection,
    handleHITLDecision,
    handleNewUpload,
    handleViewResults,
    allAgentsDone,
    awaitingDecision,
    hasStartedAnalysis,
    showUploadForm,
    validAgentsData,
    wsConnectionError,
  } = useInvestigation(playSound);

  // Derive progress text for accessibility (NVDA)
  const runningAgentNames = Object.keys(agentUpdates)
    .map((id) => validAgentsData.find((a) => a.id === id)?.name)
    .filter((n): n is Exclude<typeof n, undefined> => n !== undefined);

  let progressText = uploadPhaseText || "Establishing secure forensic pipeline…";
  if (awaitingDecision) {
    progressText = "Analysis complete. Preparing report…";
  } else if (phase === "deep" && (status === "complete" || allAgentsDone)) {
    progressText = "Deep analysis complete. All findings collected.";
  } else if (runningAgentNames.length > 0) {
    progressText = `${validCompletedAgents.length}/${validAgentsData.length} complete — ${runningAgentNames.length} agents scanning…`;
  }

  return (
    <div className="min-h-screen text-foreground px-4 sm:px-6 pt-24 pb-24 overflow-x-hidden relative font-sans select-none">
      <AnimatePresence>
        {showLoadingOverlay && (
          <AnalysisProgressOverlay
            isVisible={showLoadingOverlay}
            title="Analysis Pipeline"
            message={pipelineMessage || uploadPhaseText || "Preparing evidence..."}
          />
        )}
      </AnimatePresence>

      {/* Council Overlay removed: Now integrated into AgentProgressDisplay Header */}

      <main className="max-w-[1560px] mx-auto relative z-10 w-full">
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
                onNewUpload={handleNewUpload}
                onViewResults={handleViewResults}
                playSound={playSound}
                isNavigating={isNavigating}
                mimeType={storage.getItem<string>(FORENSIC_MIME_TYPE_KEY) ?? undefined}
              />
            )}

            <ForensicErrorModal
              isVisible={!!(errorMessage || wsConnectionError || validationError)}
              message={errorMessage || wsConnectionError || validationError || "The analysis pipeline was interrupted."}
              errorCode={errorMessage ? "0xFC_PIPELINE_HALT" : wsConnectionError ? "0xFC_CONN_FAIL" : "0xFC_VALIDATION_FAIL"}
              onRetry={wsConnectionError ? retryWsConnection : (!!file ? () => triggerAnalysis(file as File) : undefined)}
              onHome={handleNewUpload}
            />

            {!showUploadForm && !hasStartedAnalysis && !showLoadingOverlay && !validationError && (
              <div className="flex flex-col items-center justify-center min-h-[50vh] gap-4 text-center px-6">
                <p className="text-sm text-foreground/55 max-w-md">
                  Initializing the forensic workspace...
                </p>
                <button
                  type="button"
                  onClick={() => {
                    setAutoStartBlocking(false);
                    setShowLoadingOverlay(false);
                    sessionOnlyStorage.removeItem(FC_SHOW_LOADING_KEY);
                    sessionOnlyStorage.removeItem(FORENSIC_AUTO_START_KEY);
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
