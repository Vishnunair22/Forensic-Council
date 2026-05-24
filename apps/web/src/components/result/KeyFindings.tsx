"use client";

import React from "react";
import { AlertCircle, AlertTriangle, CheckCircle2 } from "lucide-react";
import { motion, useReducedMotion } from "framer-motion";
import { clsx } from "clsx";
import { cleanFindingText } from "@/lib/findingText";

interface KeyFindingsProps {
  findings: string[];
}

type Severity = "danger" | "warning" | "info" | "neutral";

function classifySeverity(text: string): Severity {
  const lower = text.toLowerCase();
  if (/tamper|manipulat|fabricat|synthetic|forged|splic|confirmed anomaly|malware|payload|deepfake|ai.generat|artificially generated|generated image/.test(lower)) return "danger";
  if (/limited|missing|absent|risk|cannot|inconclusive|warning|uncertain|coverage/.test(lower)) return "warning";
  if (/bypassed|not applicable|no readable text|no visible text/.test(lower)) return "neutral";
  return "info";
}

const DOT_COLOR: Record<Severity, string> = {
  danger:  "bg-danger",
  warning: "bg-warning",
  info:    "bg-success/80",
  neutral: "bg-white/25",
};

const TONE_CFG = {
  danger:  {
    leftBorder: "border-l-danger/50",
    badgeCls:   "text-danger  bg-danger/10  border-danger/25",
    Icon:       AlertCircle,
    label:      "Anomalies Detected",
    iconCls:    "text-danger/60",
  },
  warning: {
    leftBorder: "border-l-warning/45",
    badgeCls:   "text-warning bg-warning/10 border-warning/25",
    Icon:       AlertTriangle,
    label:      "Review Recommended",
    iconCls:    "text-warning/60",
  },
  info: {
    leftBorder: "border-l-success/45",
    badgeCls:   "text-success bg-success/10 border-success/25",
    Icon:       CheckCircle2,
    label:      "No Anomalies Detected",
    iconCls:    "text-success/60",
  },
} as const;

export function KeyFindings({ findings }: KeyFindingsProps) {
  const prefersReduced = useReducedMotion();
  const clean = findings.map((f) => cleanFindingText(f)).filter(Boolean) as string[];
  if (clean.length === 0) return null;

  const severities = clean.map(classifySeverity);
  const hasDanger  = severities.includes("danger");
  const hasWarning = severities.includes("warning");
  const overallTone = hasDanger ? "danger" : hasWarning ? "warning" : "info";
  const cfg = TONE_CFG[overallTone];
  const { Icon } = cfg;

  return (
    <section
      className={clsx("relative flex flex-col overflow-hidden fc-surface border-l-2", cfg.leftBorder)}
      aria-label="Key findings"
    >
      {/* Header */}
      <div className="px-6 py-4 border-b border-white/[0.06] flex items-center gap-2.5">
        <Icon className={clsx("w-4 h-4 shrink-0", cfg.iconCls)} />
        <h2 className="text-sm font-bold fc-text-primary">Key Findings</h2>
        <span className={clsx("ml-auto text-xs font-semibold tracking-wide px-2.5 py-1 rounded-full border", cfg.badgeCls)}>
          {cfg.label}
        </span>
      </div>

      {/* Findings as prose */}
      <div className="px-6 py-5 space-y-3.5">
        {clean.map((finding, i) => (
          <motion.div
            key={`${i}-${finding.slice(0, 20)}`}
            initial={prefersReduced ? false : { opacity: 0, y: 3 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: prefersReduced ? 0 : i * 0.06, duration: 0.18, ease: "easeOut" }}
            className="flex items-start gap-3"
          >
            <span
              className={clsx("w-1.5 h-1.5 rounded-full shrink-0 mt-[0.45em]", DOT_COLOR[severities[i]])}
              aria-hidden="true"
            />
            <p className="text-base leading-relaxed fc-text-secondary">{finding}</p>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
