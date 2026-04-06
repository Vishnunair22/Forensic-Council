"use client";

import { BarChart2, Hash, AlertCircle } from "lucide-react";
import clsx from "clsx";
import type { ReportDTO } from "@/lib/api";
import { SurfaceCard } from "@/components/ui/SurfaceCard";

interface MetricsPanelProps {
  report: ReportDTO;
  activeAgentIds: string[];
  keyFindings: string[];
}

function ConfidenceBar({ value, color }: { value: number; color: string }) {
  return (
    <div className="flex items-center gap-2 min-w-0">
      <div
        className="h-1.5 rounded-full flex-1 bg-white/[0.06] overflow-hidden"
        role="meter"
        aria-valuenow={Math.round(value * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${Math.round(value * 100)}%`, background: color }}
        />
      </div>
      <span className="text-[10px] font-mono font-bold tabular-nums shrink-0" style={{ color }}>
        {Math.round(value * 100)}%
      </span>
    </div>
  );
}

const AGENT_ACCENT: Record<string, { color: string; label: string }> = {
  Agent1: { color: "#22d3ee", label: "Image" },
  Agent2: { color: "#818cf8", label: "Audio" },
  Agent3: { color: "#38bdf8", label: "Object" },
  Agent4: { color: "#2dd4bf", label: "Video" },
  Agent5: { color: "#60a5fa", label: "Metadata" },
};

export function MetricsPanel({ report, activeAgentIds, keyFindings }: MetricsPanelProps) {
  return (
    <section aria-label="Metrics and key findings" className="space-y-4">
      <div className="flex items-center gap-2 mb-1">
        <BarChart2 className="w-3.5 h-3.5 text-white/30" aria-hidden="true" />
        <h2 className="text-[10px] font-mono font-bold uppercase tracking-widest text-white/35">
          Metrics & Findings
        </h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* ── Per-agent confidence ── */}
        <SurfaceCard className="space-y-3">
          <p className="text-[9px] font-mono font-bold uppercase tracking-widest text-white/30 mb-3">
            Agent Confidence
          </p>
          {activeAgentIds.length === 0 ? (
            <p className="text-xs text-white/25">No agents ran.</p>
          ) : (
            activeAgentIds.map((agentId) => {
              const metrics = report.per_agent_metrics?.[agentId];
              const conf = metrics?.confidence_score ?? 0;
              const accent = AGENT_ACCENT[agentId] ?? { color: "#94a3b8", label: agentId };
              return (
                <div key={agentId} className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span
                      className="text-[10px] font-bold uppercase tracking-wide"
                      style={{ color: accent.color }}
                    >
                      {accent.label}
                    </span>
                    {metrics?.skipped && (
                      <span className="text-[8px] font-mono text-white/20 uppercase">skipped</span>
                    )}
                  </div>
                  {!metrics?.skipped && (
                    <ConfidenceBar value={conf} color={accent.color} />
                  )}
                </div>
              );
            })
          )}
        </SurfaceCard>

        {/* ── Pipeline stats ── */}
        <SurfaceCard>
          <p className="text-[9px] font-mono font-bold uppercase tracking-widest text-white/30 mb-3">
            Pipeline Stats
          </p>
          <dl className="space-y-2.5">
            {[
              {
                label: "Confidence",
                value: `${Math.round((report.overall_confidence ?? 0) * 100)}%`,
                color:
                  (report.overall_confidence ?? 0) >= 0.75
                    ? "text-emerald-400"
                    : (report.overall_confidence ?? 0) >= 0.5
                      ? "text-amber-400"
                      : "text-red-400",
              },
              {
                label: "Error Rate",
                value: `${Math.round((report.overall_error_rate ?? 0) * 100)}%`,
                color:
                  (report.overall_error_rate ?? 0) <= 0.1
                    ? "text-emerald-400"
                    : "text-amber-400",
              },
              {
                label: "Agents Active",
                value: String(report.applicable_agent_count ?? activeAgentIds.length),
                color: "text-white/70",
              },
              ...(report.confidence_min !== undefined &&
              report.confidence_max !== undefined
                ? [
                    {
                      label: "Conf. Range",
                      value: `${Math.round(report.confidence_min * 100)}–${Math.round(report.confidence_max * 100)}%`,
                      color: "text-white/50",
                    },
                  ]
                : []),
            ].map(({ label, value, color }) => (
              <div key={label} className="flex items-center justify-between gap-2">
                <dt className="text-[10px] text-white/35 font-mono">{label}</dt>
                <dd className={clsx("text-[11px] font-bold font-mono tabular-nums", color)}>
                  {value}
                </dd>
              </div>
            ))}
          </dl>
        </SurfaceCard>
      </div>

      {/* ── Key findings ── */}
      {keyFindings.length > 0 && (
        <SurfaceCard className="space-y-3">
          <div className="flex items-center gap-2 mb-1">
            <Hash className="w-3.5 h-3.5 text-amber-400/60" aria-hidden="true" />
            <p className="text-[9px] font-mono font-bold uppercase tracking-widest text-white/30">
              Key Findings
            </p>
          </div>
          <ul className="space-y-2" aria-label="Key forensic findings">
            {keyFindings.map((finding, i) => (
              <li key={i} className="flex items-start gap-2">
                <AlertCircle
                  className="w-3.5 h-3.5 text-amber-400/50 shrink-0 mt-0.5"
                  aria-hidden="true"
                />
                <p className="text-[11px] text-white/60 leading-relaxed">{finding}</p>
              </li>
            ))}
          </ul>
        </SurfaceCard>
      )}

      {/* ── Reliability note ── */}
      {report.reliability_note && (
        <div className="rounded-xl border border-white/[0.05] bg-white/[0.02] px-4 py-3">
          <p className="text-[9px] font-mono font-bold uppercase tracking-widest text-white/25 mb-1">
            Reliability Note
          </p>
          <p className="text-[11px] text-white/45 leading-relaxed">
            {report.reliability_note}
          </p>
        </div>
      )}
    </section>
  );
}
