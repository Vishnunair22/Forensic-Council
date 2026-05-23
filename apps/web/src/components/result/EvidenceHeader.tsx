"use client";

import React from "react";
import { Image as ImageIcon, Film, Mic, FileText, Calendar } from "lucide-react";

interface EvidenceHeaderProps {
  fileName: string | null;
  mimeType: string | null;
  thumbnail: string | null;
  pipelineStartAt: string | null;
  caseId: string | null;
}

function mimeCategory(mime?: string | null): "image" | "video" | "audio" | "doc" {
  if (!mime) return "doc";
  if (mime.startsWith("image/")) return "image";
  if (mime.startsWith("video/")) return "video";
  if (mime.startsWith("audio/")) return "audio";
  return "doc";
}

const CAT_ICON = { image: ImageIcon, video: Film, audio: Mic, doc: FileText } as const;

function EvidencePreview({
  thumbnail,
  mimeType,
  fileName,
}: {
  thumbnail: string | null;
  mimeType: string | null;
  fileName: string;
}) {
  const cat = mimeCategory(mimeType);
  const Icon = CAT_ICON[cat];

  if ((cat === "image" || cat === "video") && thumbnail) {
    return (
      /* eslint-disable-next-line @next/next/no-img-element */
      <img
        src={thumbnail}
        alt={`Evidence: ${fileName}`}
        className="w-full h-full object-cover"
        loading="lazy"
        decoding="async"
      />
    );
  }

  return (
    <div className="w-full h-full flex items-center justify-center bg-primary/[0.07]">
      <Icon className="w-5 h-5 text-primary/60" aria-hidden="true" />
    </div>
  );
}

function formatUploadDate(iso: string): string {
  try {
    const d = new Date(iso);
    const day = d.getDate();
    const ordinals = ["th", "st", "nd", "rd"];
    const mod = day % 100;
    const suffix = ordinals[(mod - 20) % 10] ?? ordinals[mod] ?? "th";
    const month = d.toLocaleDateString("en-US", { month: "long" });
    const year = d.getFullYear();
    const time = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
    return `${month} ${day}${suffix} ${year} · ${time}`;
  } catch {
    return iso;
  }
}

function shortId(id: string): string {
  return id.length > 16 ? `…${id.slice(-12)}` : id;
}

export function EvidenceHeader({
  fileName,
  mimeType,
  thumbnail,
  pipelineStartAt,
  caseId,
}: EvidenceHeaderProps) {
  const displayName = fileName || "Evidence File";

  return (
    <section className="relative overflow-hidden fc-surface" aria-label="Evidence file">
      <div className="flex items-center gap-3 px-5 py-3 sm:px-6">
        {/* Compact thumbnail */}
        <div className="shrink-0 w-10 h-10 rounded-lg border border-white/[0.08] overflow-hidden bg-white/[0.03]">
          <EvidencePreview thumbnail={thumbnail} mimeType={mimeType} fileName={displayName} />
        </div>

        {/* File identity */}
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2 min-w-0">
            <span className="text-sm font-bold fc-text-primary truncate">{displayName}</span>
            {mimeType && (
              <span className="text-xs font-mono fc-text-muted shrink-0 hidden sm:inline">{mimeType}</span>
            )}
          </div>
          {pipelineStartAt && (
            <div className="flex items-center gap-1 mt-0.5">
              <Calendar className="w-3 h-3 fc-text-muted shrink-0" aria-hidden="true" />
              <span className="text-xs font-mono fc-text-muted">{formatUploadDate(pipelineStartAt)}</span>
            </div>
          )}
        </div>

        {/* Case ID */}
        {caseId && (
          <div className="shrink-0 text-right hidden sm:block">
            <div className="fc-eyebrow fc-text-muted">Case</div>
            <div className="text-xs font-mono fc-text-muted mt-0.5">{shortId(caseId)}</div>
          </div>
        )}
      </div>
    </section>
  );
}
