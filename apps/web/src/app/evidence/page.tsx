"use client";

import { useCallback, useRef } from "react";
import dynamic from "next/dynamic";
import { motion } from "framer-motion";
import { Shield, CloudUpload, CheckCircle2, Cpu, Scale } from "lucide-react";

import { GlassPanel } from "@/components/ui/GlassPanel";
import { LoadingOverlay } from "@/components/ui/LoadingOverlay";
import { useInvestigation } from "@/hooks/useInvestigation";
import { useSound } from "@/hooks/useSound";
import { storage } from "@/lib/storage";

const AgentProgressDisplay = dynamic(
  () => import("@/components/evidence/AgentProgressDisplay").then((mod) => mod.AgentProgressDisplay),
  { loading: () => <div className="min-h-[60vh]" /> },
);
const HITLCheckpointModal = dynamic(
  () => import("@/components/evidence/HITLCheckpointModal").then((mod) => mod.HITLCheckpointModal),
  { ssr: false },
);

export default function EvidenceUploadPage() {
  const { playSound } = useSound();
  const investigation = useInvestigation(playSound);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    investigation.setIsDragging(true);
  }, [investigation]);

  const onDragLeave = useCallback(() => {
    investigation.setIsDragging(false);
  }, [investigation]);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    investigation.setIsDragging(false);
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) investigation.handleFile(dropped);
  }, [investigation]);

  const onFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) investigation.handleFile(selected);
  };

  const startAnalysis = () => {
    if (investigation.file) void investigation.triggerAnalysis(investigation.file);
  };

  const showAgentProgress = investigation.hasStartedAnalysis && !investigation.showUploadForm;

  return (
    <main className="relative min-h-screen px-6 py-32 overflow-hidden">
      {investigation.showLoadingOverlay && (
        <LoadingOverlay
          variant="minimal"
          liveText={investigation.uploadPhaseText || investigation.pipelineMessage || "Initializing Workspace..."}
          dispatchedCount={Object.keys(investigation.agentUpdates).length}
          totalAgents={5}
        />
      )}

      {investigation.arbiterDeliberating && (
        <LoadingOverlay
          variant="minimal"
          title="Council Deliberation"
          subtitle="Arbiter Protocol"
          liveText={investigation.arbiterLiveText || "Backend arbiter synthesizing initial agent findings..."}
          dispatchedCount={5}
          totalAgents={5}
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
            pipelineMessage={investigation.arbiterLiveText || investigation.pipelineMessage}
            sessionId={storage.getItem("forensic_session_id")}
            onNewUpload={investigation.handleNewUpload}
            onViewResults={investigation.handleViewResults}
            onAcceptAnalysis={investigation.handleAcceptAnalysis}
            onRunDeepAnalysis={investigation.handleDeepAnalysis}
            isNavigating={investigation.isNavigating}
            mimeType={investigation.file?.type || storage.getItem("forensic_mime_type") || undefined}
            playSound={playSound}
            revealQueue={investigation.revealQueue}
            revealPending={investigation.revealPending}
            arbiterDeliberating={investigation.arbiterDeliberating}
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
          <div className="absolute inset-0 pointer-events-none overflow-hidden -z-10">
            <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-primary/5 blur-[120px] rounded-full" />
            <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-primary/5 blur-[120px] rounded-full" />
          </div>

          <div className="w-full max-w-xl mx-auto space-y-8 relative z-10">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6 }}
              className="text-center space-y-4"
            >
              <div className="flex items-center justify-center gap-2 opacity-40">
                <Shield className="w-4 h-4 text-primary" />
                <span className="text-[10px] uppercase tracking-[0.3em] font-mono font-black">
                  Intake Protocol
                </span>
              </div>
              <h1 className="text-4xl md:text-5xl font-extrabold tracking-tighter leading-none text-white">
                Evidence Submission
              </h1>
              <p className="text-base text-white/40 font-medium max-w-md mx-auto leading-relaxed">
                Upload digital artifacts directly into the multi-agent verification pipeline.
              </p>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.1 }}
            >
              <GlassPanel
                className={`relative p-12 rounded-[2.5rem] border-2 transition-all duration-500 overflow-hidden group ${
                  investigation.isDragging
                    ? "border-primary bg-primary/5 shadow-[0_0_50px_rgba(var(--color-primary-rgb),0.2)]"
                    : "border-white/5 bg-[#020203]/60"
                }`}
                data-testid="evidence-upload-dropzone"
                onDragOver={onDragOver}
                onDragLeave={onDragLeave}
                onDrop={onDrop}
              >
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={onFileSelect}
                  className={investigation.file ? "hidden" : "absolute inset-0 w-full h-full opacity-0 cursor-pointer z-20"}
                  id="file-upload"
                  aria-label="select evidence file"
                />

                <div className="flex flex-col items-center text-center gap-8">
                  <div className={`w-20 h-20 rounded-3xl flex items-center justify-center transition-all duration-500 ${
                    investigation.file
                      ? "bg-primary/20 border-primary/40 text-primary shadow-[0_0_30px_rgba(var(--color-primary-rgb),0.3)]"
                      : "bg-white/5 border-white/10 text-white/20 group-hover:text-white/40 group-hover:border-white/20"
                  } border`}>
                    {investigation.file ? (
                      <CheckCircle2 className="w-10 h-10 animate-in zoom-in duration-500" />
                    ) : (
                      <CloudUpload className="w-10 h-10" />
                    )}
                  </div>

                  {investigation.file ? (
                    <div className="space-y-3">
                      <p className="text-lg font-bold text-white truncate max-w-xs mx-auto">
                        {investigation.file.name}
                      </p>
                      <div className="flex items-center justify-center gap-3">
                        <span className="text-[10px] font-mono font-black text-primary/60 uppercase tracking-widest px-2 py-1 rounded bg-primary/10 border border-primary/20">
                          {(investigation.file.size / 1024 / 1024).toFixed(2)} MB
                        </span>
                        <button
                          onClick={() => investigation.setFile(null)}
                          className="text-[10px] font-mono font-black text-white/20 hover:text-red-400 transition-colors uppercase tracking-widest"
                          data-testid="evidence-clear-btn"
                        >
                          [ Remove_File ]
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <p className="text-lg font-bold text-white tracking-tight">
                        Drag and drop artifact
                      </p>
                      <p className="text-xs text-white/40 font-medium">
                        or{" "}
                        <button
                          type="button"
                          onClick={() => fileInputRef.current?.click()}
                          className="text-primary hover:underline font-bold"
                          data-testid="evidence-select-btn"
                        >
                          browse filesystem
                        </button>
                      </p>
                    </div>
                  )}
                </div>

                <div className="absolute top-4 right-4 opacity-10">
                  <Cpu className="w-8 h-8 text-primary" />
                </div>
              </GlassPanel>
            </motion.div>

            {investigation.validationError && (
              <p className="text-center text-sm font-semibold text-red-400">
                {investigation.validationError}
              </p>
            )}

            {investigation.authError && (
              <p className="text-center text-sm font-semibold text-red-400">
                {investigation.authError}
              </p>
            )}

            {investigation.wsConnectionError && (
              <div className="flex flex-col items-center gap-3">
                <p className="text-center text-sm font-semibold text-red-400">
                  {investigation.wsConnectionError}
                </p>
                <button className="btn-horizon-outline px-6 py-3 text-xs" onClick={investigation.retryWsConnection}>
                  Retry Stream
                </button>
              </div>
            )}

            {investigation.file && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex justify-center"
              >
                <button
                  type="button"
                  onClick={startAnalysis}
                  disabled={investigation.isUploading}
                  className={`group px-10 py-4 rounded-full bg-primary text-[#020617] text-xs font-black tracking-[0.2em] uppercase shadow-[0_0_40px_rgba(var(--color-primary-rgb),0.3)] transition-all flex items-center gap-4 ${
                    investigation.isUploading ? "opacity-50 cursor-not-allowed" : "hover:scale-105 hover:shadow-[0_0_60px_rgba(var(--color-primary-rgb),0.5)] active:scale-95"
                  }`}
                  data-testid="evidence-submit-btn"
                >
                  Commence Analysis
                  <div className="w-5 h-5 rounded-full bg-[#020617]/10 flex items-center justify-center group-hover:translate-x-1 transition-transform">
                    <Shield className="w-3 h-3" />
                  </div>
                </button>
              </motion.div>
            )}

            <div className="grid grid-cols-3 gap-8 mt-12 opacity-20 max-w-xs mx-auto">
              <div className="flex flex-col items-center gap-2">
                <Cpu className="w-4 h-4 text-primary" />
                <span className="text-[8px] uppercase tracking-tighter font-mono font-bold">Neural_Scan</span>
              </div>
              <div className="flex flex-col items-center gap-2">
                <Scale className="w-4 h-4 text-primary" />
                <span className="text-[8px] uppercase tracking-tighter font-mono font-bold">Arbiter_Sync</span>
              </div>
              <div className="flex flex-col items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-primary" />
                <span className="text-[8px] uppercase tracking-tighter font-mono font-bold">Signed_Ledger</span>
              </div>
            </div>
          </div>
        </section>
      )}
    </main>
  );
}
