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
  // No length cap on the top-level summary or key findings — these are short
  // narrative paragraphs from the Arbiter; truncating them with "..." in the
  // header was hiding the very signals the user needs to read.
  const cleanVerdictSentence = cleanFindingText(verdictSentence);
  const cleanKeyFindings = keyFindings
    .map((finding) => cleanFindingText(finding))
    .filter(Boolean);
  const notes = [
    { label: "Reliability", value: cleanFindingText(reliabilityNote) },
    { label: "Uncertainty", value: cleanFindingText(uncertaintyStatement) },
    { label: "Coverage", value: cleanFindingText(coverageNote) },
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
          <p className="mt-1 text-xs fc-text-faint">
            Arbiter-selected signals from the agent and tool outputs.
          </p>
        </div>
        <span className={clsx(
          "w-fit rounded-md border px-3 py-1.5 fc-eyebrow",
          isDeepPhase ? "text-success/75 border-success/20 bg-success/5" : "fc-text-faint border-white/10 bg-white/[0.025]",
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
                className="p-5 border border-white/5 bg-[#02040A] rounded-2xl shadow-xl"
              >
                <div className="flex items-start gap-4">
                  <FindingIcon severity={severity} />
                  <div className="min-w-0">
                    <div className="fc-eyebrow fc-text-faint">
                      Signal {String(i + 1).padStart(2, "0")}
                    </div>
                    <p className="mt-2 text-sm fc-text-muted leading-relaxed">
                      {finding}
                    </p>
                  </div>
                </div>
              </motion.article>
            );
          })}
        </div>
      )}

      <div className="border border-white/5 bg-[#02040A] rounded-2xl shadow-xl p-5 md:p-6">
        <div className="flex items-start gap-4">
          <div className="w-10 h-10 border border-white/5 bg-transparent flex items-center justify-center shrink-0 rounded-xl">
            <Info className="w-4 h-4 text-primary/70" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="fc-eyebrow fc-text-faint">
              Arbiter Summary
            </div>
            {cleanVerdictSentence && (
              <p className="mt-2 text-sm md:text-base fc-text-secondary leading-relaxed">
                {cleanVerdictSentence}
              </p>
            )}

            {(notes.length > 0 || skipped.length > 0) && (
              <div className="mt-5 grid grid-cols-1 md:grid-cols-3 gap-3">
                {notes.map((note) => (
                  <div key={note.label} className="border-t border-white/5 pt-4">
                    <div className="fc-eyebrow fc-text-faint">
                      {note.label}
                    </div>
                    <p className="mt-2 text-xs fc-text-muted leading-relaxed">
                      {note.value}
                    </p>
                  </div>
                ))}
                {skipped.length > 0 && (
                  <div className="border-t border-white/5 pt-4">
                    <div className="fc-eyebrow fc-text-faint">
                      Skipped Agents
                    </div>
                    <p className="mt-2 text-xs fc-text-muted leading-relaxed">
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
  const base = "w-9 h-9 shrink-0 flex items-center justify-center border mt-0.5 rounded-xl";
  if (severity === "danger") {
    return (
      <div className={clsx(base, "bg-danger/10 border-danger/30 text-danger")}>
        <AlertCircle className="w-4 h-4" />
      </div>
    );
  }
  if (severity === "warning") {
    return (
      <div className={clsx(base, "bg-warning/10 border-warning/30 text-warning")}>
        <Minus className="w-4 h-4" />
      </div>
    );
  }
  if (severity === "neutral") {
    return (
      <div className={clsx(base, "bg-transparent border-white/5 text-white/35")}>
        <CircleDashed className="w-4 h-4" />
      </div>
    );
  }
  return (
    <div className={clsx(base, "bg-white text-black")}>
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
