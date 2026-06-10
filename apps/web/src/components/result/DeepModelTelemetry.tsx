"use client";

import React from "react";
import { Cpu } from "lucide-react";
import { motion } from "framer-motion";
import { ReportDTO } from "@/lib/api";

interface DeepModelTelemetryProps {
  report: ReportDTO;
}

// Honest tool labels — the real method each tool runs, no fabricated SOTA model
// names. TruFor (splicing) and the diffusion/ai-gen detector are real learned
// models; copy-move, anomaly, and frequency checks are classical screening-tier.
const TOOL_LABELS: Record<string, string> = {
  neural_copy_move: "Copy-Move Screening",
  neural_splicing: "TruFor Splicing Localization",
  anomaly_tracer: "Anomaly Screening (One-Class SVM)",
  f3_net_frequency: "Frequency Screening (DWT/FFT)",
  neural_ela: "Neural Error-Level Analysis",
  diffusion_artifact_detector: "Diffusion Artifact Detector",
  visual_evidence_profile: "Visual Evidence Profile",
};

// Tools backed by a real learned model that can ASSERT a finding, vs classical
// screening-tier checks that only flag for review (non-asserting). Drives the
// honest per-row tier label instead of the old invented "Transformer V2/Tensor V4".
const ASSERTING_MODELS = new Set([
  "neural_splicing",
  "diffusion_artifact_detector",
  "neural_ela",
  "visual_evidence_profile",
]);

export function DeepModelTelemetry({ report }: DeepModelTelemetryProps) {
  const allFindings = Object.values(report.per_agent_findings ?? {}).flat();
  const deepFindings = allFindings.filter(
    (f) => f != null && (f.metadata as Record<string, unknown>)?.analysis_phase === "deep",
  );

  if (deepFindings.length === 0) return null;
  if (!report.cross_modal_fusion || Object.keys(report.cross_modal_fusion).length === 0) return null;

  const models = Array.from(
    new Set(deepFindings.map((f) => f.finding_type).filter(Boolean))
  );

  return (
    <div className="relative flex flex-col overflow-hidden fc-surface">
      {/* Header */}
      <div className="px-5 py-3.5 border-b border-white/[0.06] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Cpu className="w-3.5 h-3.5 text-primary/60" />
          <span className="fc-eyebrow fc-text-muted">
            Deep Model Telemetry
          </span>
        </div>
        <span className="fc-eyebrow fc-text-muted">
          {models.length} model{models.length === 1 ? "" : "s"} · deep pass
        </span>
      </div>

      {/* Elevated Model Rows */}
      <div className="p-6 bg-[radial-gradient(ellipse_at_top,rgba(255,255,255,0.02),transparent_50%)]">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-8 gap-y-6">
          {models.slice(0, 6).map((model, index) => {
            const modelFindings = deepFindings.filter((f) => f.finding_type === model);
            const count = modelFindings.length;
            const avgConf = Math.round(
              (modelFindings.reduce((acc, f) => acc + (f.raw_confidence_score ?? f.confidence_raw ?? 0), 0) / count) * 100,
            );

            const totalBlocks = 25;
            const activeBlocks = Math.round((avgConf / 100) * totalBlocks);

            return (
              <motion.div
                key={model}
                initial={{ opacity: 0, y: 5 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.05 }}
                className="space-y-3 relative group"
              >
                <div className="absolute -inset-x-3 -inset-y-2 border border-white/0 group-hover:border-white/5 bg-transparent group-hover:bg-white/[0.01] rounded-lg transition-all pointer-events-none" />

                <div className="flex items-center justify-between relative z-10">
                  <div className="flex items-center gap-2.5">
                    <div className="w-1.5 h-1.5 rounded-sm bg-primary/40 group-hover:bg-primary transition-colors" />
                    <span className="text-xs font-mono text-white/90 tracking-widest uppercase">
                      {TOOL_LABELS[model] || model.replace(/_/g, " ").toUpperCase()}
                    </span>
                  </div>
                  <span className="text-sm font-mono font-bold text-primary">
                    {avgConf}%
                  </span>
                </div>

                {/* Segmented Neural Activation Bar */}
                <div className="flex gap-[2px] h-2 w-full relative z-10" aria-label={`${model} confidence`}>
                  {Array.from({ length: totalBlocks }).map((_, i) => (
                    <div
                      key={i}
                      className="flex-1 rounded-sm transition-all duration-300"
                      style={{
                        backgroundColor: i < activeBlocks
                          ? `rgba(var(--color-primary-rgb), ${0.4 + (i / totalBlocks) * 0.6})`
                          : 'rgba(255,255,255,0.05)',
                        boxShadow: 'none',
                      }}
                    />
                  ))}
                </div>

                <div className="flex justify-between items-center text-xs font-mono fc-text-muted uppercase tracking-widest relative z-10">
                  <span>
                    {ASSERTING_MODELS.has(model) ? "Asserting model" : "Screening tier"}
                  </span>
                  <span>{count} run{count !== 1 ? "s" : ""}</span>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
