"use client";

import React from "react";
import { Cpu, Zap } from "lucide-react";
import { ReportDTO } from "@/lib/api";

interface DeepModelTelemetryProps {
  report: ReportDTO;
}

const TOOL_LABELS: Record<string, string> = {
  neural_copy_move: "BusterNet-V2 (SOTA)",
  neural_splicing: "TruFor Transformer",
  anomaly_tracer: "ManTra-Net Tracer",
  f3_net_frequency: "F3-Net Frequency",
  neural_ela: "Neural ELA (ViT-L)",
  diffusion_artifact_detector: "Diffusion Discriminator",
  gemini_deep_forensic: "Gemini 2.5 Multi-Modal",
};

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
        <div className="flex items-center gap-1.5">
          <div
            className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse"
          />
          <span className="fc-eyebrow fc-text-muted">
            Heavy-Compute Active
          </span>
        </div>
      </div>

      {/* Model rows */}
      <div className="p-5">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4">
          {models.slice(0, 6).map((model) => {
            const modelFindings = deepFindings.filter((f) => f.finding_type === model);
            const count = modelFindings.length;
            const avgConf = Math.round(
              (modelFindings.reduce((acc, f) => acc + (f.raw_confidence_score ?? f.confidence_raw ?? 0), 0) / count) * 100,
            );

            return (
              <div key={model} className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Zap className="w-3 h-3 text-primary/40" />
                    <span className="text-xs font-mono fc-text-secondary font-bold truncate max-w-[160px]">
                      {TOOL_LABELS[model] || model.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}
                    </span>
                  </div>
                  <span className="text-xs font-mono font-black fc-text-primary-accent">
                    {avgConf}%
                  </span>
                </div>
                <div className="h-0.5 w-full bg-white/[0.06] rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary/60 transition-[width] duration-200 ease-out"
                    style={{ width: `${avgConf}%` }}
                    role="progressbar"
                    aria-valuenow={avgConf}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={`${model} confidence`}
                  />
                </div>
                <div className="flex justify-between items-center text-xs font-mono fc-text-muted">
                  <span>
                    {model.startsWith("neural_") || model === "anomaly_tracer"
                      ? "Transformer V2"
                      : "Tensor V4"}
                  </span>
                  <span>{count} invocation{count !== 1 ? "s" : ""}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
