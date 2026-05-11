"use client";

import React from "react";
import { AlertCircle, CheckCircle2, CircleDashed, FileText, Info, Minus } from "lucide-react";
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
  const cleanVerdictSentence = cleanFindingText(verdictSentence, 320);
  const cleanKeyFindings = keyFindings
    .map((finding) => cleanFindingText(finding, 260))
    .filter(Boolean);
  const notes = [
    { label: "Reliability", value: cleanFindingText(reliabilityNote, 220) },
    { label: "Uncertainty", value: cleanFindingText(uncertaintyStatement, 220) },
    { label: "Coverage", value: cleanFindingText(coverageNote, 220) },
  ].filter((note) => note.value);
  const skipped = Object.entries(skippedAgents ?? {});

  if (!cleanVerdictSentence && cleanKeyFindings.length === 0 && notes.length === 0 && skipped.length === 0) {
    return null;
  }

  return (
    <section className="space-y-5" aria-label="Key findings">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3 px-1">
        <div>
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-primary/70" />
            <h2 className="text-lg font-heading font-bold text-white/85">Key Findings</h2>
          </div>
          <p className="mt-1 text-xs text-white/35">
            Arbiter-selected signals from the agent and tool outputs.
          </p>
        </div>
        <span className={clsx(
          "w-fit rounded-md border px-3 py-1.5 text-[9px] font-mono font-bold uppercase tracking-[0.16em]",
          isDeepPhase ? "text-success/75 border-success/20 bg-success/5" : "text-white/35 border-white/10 bg-white/[0.025]",
        )}>
          {isDeepPhase ? "Deep Analysis" : "Initial Analysis"}
        </span>
      </div>

      {cleanKeyFindings.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {cleanKeyFindings.map((finding, i) => {
            const severity = classifyFinding(finding);
            return (
              <motion.article
                key={`${i}-${finding.slice(0, 20)}`}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.035 }}
                className="rounded-xl p-5"
                style={{
                  background: "rgba(6,10,20,0.85)",
                  border: "1px solid rgba(165,200,255,0.07)",
                  boxShadow: "0 4px 20px rgba(0,0,0,0.3)",
                }}
              >
                <div className="flex items-start gap-4">
                  <FindingIcon severity={severity} />
                  <div className="min-w-0">
                    <div className="text-[9px] font-mono font-bold text-white/20 uppercase tracking-[0.18em]">
                      Signal {String(i + 1).padStart(2, "0")}
                    </div>
                    <p className="mt-2 text-sm text-white/62 leading-relaxed">
                      {finding}
                    </p>
                  </div>
                </div>
              </motion.article>
            );
          })}
        </div>
      )}

      <div className="rounded-2xl border border-white/8 bg-white/[0.025] p-5 md:p-6">
        <div className="flex items-start gap-4">
          <div className="w-10 h-10 rounded-xl border border-primary/20 bg-primary/5 flex items-center justify-center shrink-0">
            <Info className="w-4 h-4 text-primary/70" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[10px] font-mono font-bold text-white/30 uppercase tracking-[0.18em]">
              Arbiter Summary
            </div>
            {cleanVerdictSentence && (
              <p className="mt-2 text-sm md:text-base text-white/65 leading-relaxed">
                {cleanVerdictSentence}
              </p>
            )}

            {(notes.length > 0 || skipped.length > 0) && (
              <div className="mt-5 grid grid-cols-1 md:grid-cols-3 gap-3">
                {notes.map((note) => (
                  <div key={note.label} className="rounded-xl border border-white/8 bg-black/10 p-4">
                    <div className="text-[9px] font-mono font-bold text-white/25 uppercase tracking-[0.16em]">
                      {note.label}
                    </div>
                    <p className="mt-2 text-xs text-white/48 leading-relaxed">
                      {note.value}
                    </p>
                  </div>
                ))}
                {skipped.length > 0 && (
                  <div className="rounded-xl border border-white/8 bg-black/10 p-4">
                    <div className="text-[9px] font-mono font-bold text-white/25 uppercase tracking-[0.16em]">
                      Skipped Agents
                    </div>
                    <p className="mt-2 text-xs text-white/48 leading-relaxed">
                      {skipped.map(([agent, reason]) => `${agent}: ${cleanFindingText(reason, 80)}`).join("; ")}
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function FindingIcon({ severity }: { severity: "danger" | "warning" | "info" | "neutral" }) {
  const base = "w-9 h-9 shrink-0 rounded-xl flex items-center justify-center border mt-0.5";
  if (severity === "danger") {
    return (
      <div className={clsx(base, "bg-danger/10 border-danger/20 text-danger")}>
        <AlertCircle className="w-4 h-4" />
      </div>
    );
  }
  if (severity === "warning") {
    return (
      <div className={clsx(base, "bg-warning/10 border-warning/20 text-warning")}>
        <Minus className="w-4 h-4" />
      </div>
    );
  }
  if (severity === "neutral") {
    return (
      <div className={clsx(base, "bg-white/[0.03] border-white/10 text-white/35")}>
        <CircleDashed className="w-4 h-4" />
      </div>
    );
  }
  return (
    <div className={clsx(base, "bg-primary/10 border-primary/20 text-primary")}>
      <CheckCircle2 className="w-4 h-4" />
    </div>
  );
}

function classifyFinding(finding: string): "danger" | "warning" | "info" | "neutral" {
  const lower = finding.toLowerCase();
  if (/tamper|manipulat|fabricat|synthetic|forged|splic|confirmed anomaly|malware|payload/.test(lower)) {
    return "danger";
  }
  if (/limited|missing|absent|risk|cannot|inconclusive|warning|uncertain|coverage/.test(lower)) {
    return "warning";
  }
  if (/bypassed|not applicable|no readable text|no visible text/.test(lower)) {
    return "neutral";
  }
  return "info";
}
