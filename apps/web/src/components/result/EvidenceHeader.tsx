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
const CAT_COLOR = { image: "#22d3ee", video: "#38bdf8", audio: "#818cf8", doc: "#60a5fa" } as const;

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
  const color = CAT_COLOR[cat];

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
    <div
      className="w-full h-full flex flex-col items-center justify-center gap-2"
      style={{ background: `${color}10` }}
    >
      <Icon className="w-8 h-8 shrink-0" style={{ color }} aria-hidden="true" />
      <span className="text-xs font-mono font-bold tracking-wide" style={{ color: `${color}80` }}>
        {cat}
      </span>
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
    return `${month} ${day}${suffix} ${year} | ${time}`;
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
    <section className="relative flex flex-col overflow-hidden fc-surface">
      <div className="flex items-start gap-5 p-5 sm:p-6">
        {/* Square thumbnail */}
        <div className="shrink-0 w-20 h-20 sm:w-24 sm:h-24 rounded-xl border border-white/[0.08] overflow-hidden bg-white/[0.03]">
          <EvidencePreview thumbnail={thumbnail} mimeType={mimeType} fileName={displayName} />
        </div>

        {/* File info */}
        <div className="flex-1 min-w-0 py-0.5">
          <h1 className="text-base sm:text-lg font-bold text-white leading-tight truncate">
            {displayName}
          </h1>
          {mimeType && (
            <p className="text-xs font-mono fc-text-muted mt-1">{mimeType}</p>
          )}
          {pipelineStartAt && (
            <div className="flex items-center gap-1.5 mt-3">
              <Calendar className="w-3 h-3 fc-text-muted shrink-0" />
              <span className="text-xs font-mono fc-text-muted">
                Uploaded on {formatUploadDate(pipelineStartAt)}
              </span>
            </div>
          )}
        </div>

        {/* Case ID — desktop only */}
        {caseId && (
          <div className="shrink-0 text-right hidden sm:block pt-0.5">
            <div className="fc-eyebrow fc-text-muted">Case</div>
            <div className="text-xs font-mono fc-text-muted mt-1">{shortId(caseId)}</div>
          </div>
        )}
      </div>
    </section>
  );
}
