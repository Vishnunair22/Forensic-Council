"use client";

import React from "react";
import { FileText } from "lucide-react";
import { clsx } from "clsx";
import { cleanFindingText } from "@/lib/findingText";

interface ExecutiveSummaryProps {
  summary?: string;
  reliabilityNote?: string;
  isDeepPhase?: boolean;
}

export function ExecutiveSummary({
  summary,
  reliabilityNote,
  isDeepPhase = false,
}: ExecutiveSummaryProps) {
  const clean = cleanFindingText(summary);
  if (!clean) return null;

  // Render inline **bold** markers produced by the deterministic builder
  const rendered = renderInlineBold(clean);

  return (
    <section
      className="relative flex flex-col overflow-hidden fc-surface"
      aria-label="Executive summary"
    >
      <div className="px-6 py-4 border-b border-white/[0.06] flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-primary/60" />
          <h2 className="text-sm font-bold fc-text-secondary">Executive Summary</h2>
        </div>
        <span
          className={clsx(
            "fc-eyebrow px-2.5 py-1 rounded border",
            isDeepPhase
              ? "text-[#bbf7d0] border-success/20 bg-success/5"
              : "fc-text-muted border-white/10"
          )}
        >
          {isDeepPhase ? "Deep Analysis" : "Initial Analysis"}
        </span>
      </div>

      <div className="p-6 md:p-8 space-y-4">
        <p className="text-sm md:text-[15px] fc-text-secondary leading-relaxed font-medium">
          {rendered}
        </p>

        {reliabilityNote && (
          <p className="text-xs fc-text-muted leading-relaxed border-t border-white/[0.04] pt-4">
            {cleanFindingText(reliabilityNote)}
          </p>
        )}
      </div>
    </section>
  );
}

function renderInlineBold(text: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={i} className="text-white font-bold">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return <React.Fragment key={i}>{part}</React.Fragment>;
  });
}
