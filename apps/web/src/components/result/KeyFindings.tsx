"use client";

import React from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, CircleDashed, Lightbulb } from "lucide-react";
import { motion } from "framer-motion";
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

const SEVERITY_CFG = {
  danger:  { cls: "bg-danger/15 border-danger/35",    Icon: AlertCircle,   color: "text-danger"   },
  warning: { cls: "bg-warning/10 border-warning/30",  Icon: AlertTriangle, color: "text-warning"  },
  info:    { cls: "bg-success/10 border-success/30",  Icon: CheckCircle2,  color: "text-success"  },
  neutral: { cls: "bg-transparent border-white/[0.1]",Icon: CircleDashed,  color: "fc-text-muted" },
} as const;

export function KeyFindings({ findings }: KeyFindingsProps) {
  const clean = findings.map((f) => cleanFindingText(f)).filter(Boolean) as string[];
  if (clean.length === 0) return null;

  return (
    <section
      className="rounded-2xl border border-white/[0.06] overflow-hidden"
      aria-label="Key findings"
    >
      <div className="px-6 py-4 border-b border-white/[0.06] flex items-center gap-2">
        <Lightbulb className="w-4 h-4 text-primary/60" />
        <h2 className="text-sm font-bold fc-text-primary">Key Findings</h2>
        <span className="fc-eyebrow fc-text-muted ml-auto">{clean.length} signal{clean.length === 1 ? "" : "s"}</span>
      </div>

      <div className="p-6 space-y-3">
        {clean.map((finding, i) => {
          const severity = classifySeverity(finding);
          const cfg = SEVERITY_CFG[severity];
          const Icon = cfg.Icon;
          return (
            <motion.div
              key={`${i}-${finding.slice(0, 20)}`}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04, duration: 0.16, ease: "easeOut" }}
              className="flex items-start gap-3"
            >
              <div className={clsx("w-5 h-5 rounded-lg flex items-center justify-center shrink-0 mt-0.5 border", cfg.cls)}>
                <Icon className={clsx("w-3 h-3", cfg.color)} />
              </div>
              <p className="text-sm fc-text-muted leading-relaxed">{finding}</p>
            </motion.div>
          );
        })}
      </div>
    </section>
  );
}
