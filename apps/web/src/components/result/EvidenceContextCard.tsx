"use client";

import React from "react";
import { ImageIcon, Sparkles, Cpu } from "lucide-react";
import { clsx } from "clsx";
import type { ReportDTO } from "@/lib/api";
import { cleanFindingText } from "@/lib/findingText";

type EvidenceSummary = NonNullable<ReportDTO["evidence_summary"]>;

const FILE_TYPE_LABELS: Record<string, string> = {
  screenshot: "Screenshot / screen capture",
  photograph: "Photograph",
  document_scan: "Scanned document",
  ai_generated: "AI-generated image",
  composite: "Composite image",
  web_image: "Web / re-uploaded image",
  unknown: "Image",
};

function prettyFileType(raw?: string): string {
  const key = String(raw || "").trim().toLowerCase();
  if (!key) return "";
  return FILE_TYPE_LABELS[key] || key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Page-level "what this shows" context, rendered ONCE above the agent cards.
 * Descriptive scene + file-type from the pre-flight VisualContext — never a
 * verdict. The per-agent cards no longer repeat this shared description.
 */
export function EvidenceContextCard({ evidenceSummary }: { evidenceSummary?: EvidenceSummary }) {
  const scene = cleanFindingText(String(evidenceSummary?.scene_description || "").trim());
  const fileType = prettyFileType(evidenceSummary?.file_type_assessment);
  if (!scene && !fileType) return null;

  const isRemote = evidenceSummary?.source === "remote_vision";

  return (
    <div className="rounded-2xl fc-surface-quiet px-6 py-5">
      <div className="flex items-center justify-between gap-3 mb-2.5">
        <div className="flex items-center gap-2.5">
          <span className="w-9 h-9 rounded-xl flex items-center justify-center border border-white/10 bg-white/[0.03]">
            <ImageIcon className="w-4.5 h-4.5 text-white/70" />
          </span>
          <h3 className="text-sm font-bold tracking-tight text-white/90">What this shows</h3>
        </div>
        <span
          className="flex items-center gap-1.5 text-xs font-semibold tracking-wide fc-text-muted px-2.5 py-1 rounded-full border border-white/10 bg-white/[0.03]"
          title={
            isRemote
              ? "Described by the cloud vision model"
              : "Described on-device — orientation only, not a court-grade reading"
          }
        >
          {isRemote ? <Sparkles className="w-3.5 h-3.5" /> : <Cpu className="w-3.5 h-3.5" />}
          {isRemote ? "Vision model" : "On-device read"}
        </span>
      </div>

      {scene && (
        <p className="text-sm fc-text-secondary leading-relaxed font-medium">{scene}</p>
      )}

      {fileType && (
        <div className="mt-3 flex items-center gap-2">
          <span
            className={clsx(
              "text-xs font-semibold tracking-wide px-2.5 py-1 rounded-md",
              "border border-white/10 bg-white/[0.04] fc-text-muted",
            )}
          >
            {fileType}
          </span>
        </div>
      )}
    </div>
  );
}
