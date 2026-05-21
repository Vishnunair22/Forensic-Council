"use client";

import React from "react";
import { AlertCircle, CheckCircle2, CircleDashed, FileText, Minus } from "lucide-react";
import { motion } from "framer-motion";
import clsx from "clsx";
import { cleanFindingText } from "@/lib/findingText";

interface IntelligenceBriefProps {
  verdictSentence?: string;
  keyFindings?: string[];
  reliabilityNote?: string;
  uncertaintyStatement?: string;
  coverageNote?: string;
  skippedAgents?: Record<string, string>;
  isDeepPhase?: boolean;
}

export function IntelligenceBrief({
  verdictSentence,
  keyFindings = [],
  reliabilityNote,
  uncertaintyStatement,
  coverageNote,
  skippedAgents,
  isDeepPhase = false,
}: IntelligenceBriefProps) {
  const cleanVerdictSentence = cleanFindingText(verdictSentence);
  const cleanKeyFindings = keyFindings
    .map((f) => cleanFindingText(f))
    .filter(Boolean);
  const notes = [
    { label: "Reliability",  value: cleanFindingText(reliabilityNote) },
    { label: "Uncertainty",  value: cleanFindingText(uncertaintyStatement) },
    { label: "Coverage",     value: cleanFindingText(coverageNote) },
  ].filter((n) => n.value);
  const skipped = Object.entries(skippedAgents ?? {});

  if (!cleanVerdictSentence && cleanKeyFindings.length === 0 && notes.length === 0 && skipped.length === 0) {
    return null;
  }

  return (
    <section
      className="rounded-2xl border border-white/[0.06] overflow-hidden"
      aria-label="Intelligence brief"
    >
      {/* Header row */}
      <div className="px-6 py-4 border-b border-white/[0.06] flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-primary/60" />
          <h2 className="text-sm font-bold text-white/85">Intelligence Brief</h2>
        </div>
        <span className={clsx(
          "fc-eyebrow px-2.5 py-1 rounded border",
          isDeepPhase
            ? "text-success/75 border-success/20 bg-success/5"
            : "fc-text-faint border-white/10"
        )}>
          {isDeepPhase ? "Deep Analysis" : "Initial Analysis"}
        </span>
      </div>

      <div className="p-6 md:p-7 space-y-5">
        {/* Arbiter summary — lead paragraph */}
        {cleanVerdictSentence && (
          <p className="text-sm md:text-[15px] text-white/80 leading-relaxed">
            {cleanVerdictSentence}
          </p>
        )}

        {/* Key signals — compact list */}
        {cleanKeyFindings.length > 0 && (
          <div className={clsx(cleanVerdictSentence && "pt-4 border-t border-white/[0.04]")}>
            <div className="fc-eyebrow fc-text-faint mb-3">Key Signals</div>
            <div className="space-y-3">
              {cleanKeyFindings.map((finding, i) => {
                const severity = classifyFinding(finding);
                return (
                  <motion.div
                    key={`${i}-${finding.slice(0, 20)}`}
                    initial={{ opacity: 0, x: -4 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.04 }}
                    className="flex items-start gap-3"
                  >
                    <FindingDot severity={severity} />
                    <p className="text-sm fc-text-muted leading-relaxed">{finding}</p>
                  </motion.div>
                );
              })}
            </div>
          </div>
        )}

        {/* Notes footer */}
        {(notes.length > 0 || skipped.length > 0) && (
          <div className="pt-4 border-t border-white/[0.04] grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
            {notes.map((note) => (
              <div key={note.label}>
                <div className="fc-eyebrow fc-text-faint mb-1">{note.label}</div>
                <p className="text-xs fc-text-muted leading-relaxed">{note.value}</p>
              </div>
            ))}
            {skipped.length > 0 && (
              <div>
                <div className="fc-eyebrow fc-text-faint mb-1">Skipped Agents</div>
                <p className="text-xs fc-text-muted leading-relaxed">
                  {skipped
                    .map(([agent, reason]) => `${agent}: ${cleanFindingText(reason, 80)}`)
                    .join("; ")}
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

function FindingDot({ severity }: { severity: "danger" | "warning" | "info" | "neutral" }) {
  const cfg = {
    danger:  { cls: "bg-danger/15 border-danger/35",   Icon: AlertCircle,  color: "text-danger"   },
    warning: { cls: "bg-warning/10 border-warning/30",  Icon: Minus,        color: "text-warning"  },
    info:    { cls: "bg-success/10 border-success/30",  Icon: CheckCircle2, color: "text-success"  },
    neutral: { cls: "bg-transparent border-white/[0.1]",Icon: CircleDashed, color: "fc-text-faint" },
  }[severity];

  return (
    <div className={clsx("w-5 h-5 rounded flex items-center justify-center shrink-0 mt-0.5 border", cfg.cls)}>
      <cfg.Icon className={clsx("w-3 h-3", cfg.color)} />
    </div>
  );
}

function classifyFinding(finding: string): "danger" | "warning" | "info" | "neutral" {
  const lower = finding.toLowerCase();
  if (/tamper|manipulat|fabricat|synthetic|forged|splic|confirmed anomaly|malware|payload/.test(lower)) return "danger";
  if (/limited|missing|absent|risk|cannot|inconclusive|warning|uncertain|coverage/.test(lower)) return "warning";
  if (/bypassed|not applicable|no readable text|no visible text/.test(lower)) return "neutral";
  return "info";
}
