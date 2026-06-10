"use client";

import React from "react";
import { ImageIcon, Sparkles, Cpu, AudioLines, Film, FileText, ChevronDown } from "lucide-react";
import { clsx } from "clsx";
import type { ReportDTO } from "@/lib/api";
import { cleanFindingText } from "@/lib/findingText";

type EvidenceSummary = NonNullable<ReportDTO["evidence_summary"]>;
type EvidenceDetails = NonNullable<EvidenceSummary["details"]>;

// Ordered detail groups: content → integrity → provenance. `alert` groups (signals)
// get a subtle amber tint; `text` groups render as lines, the rest as chips.
const DETAIL_GROUPS: Array<{ key: keyof EvidenceDetails; label: string; kind?: "text" | "alert" }> = [
  { key: "objects", label: "Objects / entities" },
  { key: "people", label: "People" },
  { key: "weapons", label: "Weapons / dangerous items", kind: "alert" },
  { key: "documents", label: "Documents / IDs" },
  { key: "extracted_text", label: "Extracted text", kind: "text" },
  { key: "scene_inconsistencies", label: "Scene inconsistencies", kind: "alert" },
  { key: "ai_generation_signals", label: "AI-generation signals", kind: "alert" },
  { key: "manipulation_signals", label: "Manipulation signals", kind: "alert" },
  { key: "device_platform", label: "Device / platform" },
  { key: "software", label: "Software / app" },
  { key: "timestamps", label: "Visible timestamps" },
  { key: "location_clues", label: "Location clues" },
  { key: "metadata_notes", label: "Notes", kind: "text" },
];

const FILE_TYPE_LABELS: Record<string, string> = {
  screenshot: "Screenshot / screen capture",
  photograph: "Photograph",
  document_scan: "Scanned document",
  ai_generated: "AI-generated image",
  composite: "Composite image",
  web_image: "Web / re-uploaded image",
  unknown: "Image",
};

type Modality = "image" | "audio" | "video" | "document";

function modalityOf(mimeType?: string | null): Modality {
  const m = (mimeType || "").toLowerCase();
  if (m.startsWith("audio/")) return "audio";
  if (m.startsWith("video/")) return "video";
  if (m === "application/pdf" || m.startsWith("text/") || m.includes("document")) return "document";
  return "image";
}

function prettyFileType(raw: string | undefined, modality: Modality): string {
  const key = String(raw || "").trim().toLowerCase();
  // For non-image evidence the backend's image-oriented file_type_assessment is
  // often "unknown" — fall back to a modality label rather than mislabelling "Image".
  if (!key || key === "unknown") {
    return { audio: "Audio recording", video: "Video clip", document: "Document", image: key ? "Image" : "" }[modality];
  }
  return FILE_TYPE_LABELS[key] || key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Page-level "what this shows" context, rendered ONCE above the agent cards.
 * Descriptive scene + file-type from the pre-flight VisualContext — never a
 * verdict. The per-agent cards no longer repeat this shared description.
 */
export function EvidenceContextCard({
  evidenceSummary,
  mimeType,
}: {
  evidenceSummary?: EvidenceSummary;
  mimeType?: string | null;
}) {
  const [open, setOpen] = React.useState(false);
  const modality = modalityOf(mimeType);
  let scene = cleanFindingText(String(evidenceSummary?.scene_description || "").trim());
  // Never surface the image-ensemble fallback ("CLIP classified the image as
  // unknown. Forensic signals: ELA/...") on a non-image card — it is meaningless
  // for audio/video/document content (it appears when the native content read
  // falls back to the local image ensemble).
  if (
    modality !== "image" &&
    /^clip classified|^identified as:|forensic signals: ela|forensic screening surfaced|visual content could not|resolution:.*px/i.test(scene)
  ) {
    scene = "";
  }
  const fileType = prettyFileType(evidenceSummary?.file_type_assessment, modality);
  if (!scene && !fileType) return null;

  const details = evidenceSummary?.details;
  const presentGroups = DETAIL_GROUPS.filter((g) => {
    const v = details?.[g.key];
    return Array.isArray(v) && v.length > 0;
  });
  const integrityRead =
    typeof details?.integrity_assessment === "string" ? details.integrity_assessment.trim() : "";
  const hasDetails = presentGroups.length > 0 || !!integrityRead;

  const isRemote = evidenceSummary?.source === "remote_vision";
  // Modality-aware header, icon and provenance label — "Visual"/"shows" is wrong
  // for audio/document evidence.
  const heading = { image: "What this shows", audio: "What this contains", video: "What this shows", document: "What this contains" }[modality];
  const ModalityIcon = { image: ImageIcon, audio: AudioLines, video: Film, document: FileText }[modality];
  const remoteLabel = modality === "image" ? "Vision model" : "Content model";

  return (
    <div className="rounded-2xl fc-surface-quiet px-6 py-5">
      <div className="flex items-center justify-between gap-3 mb-2.5">
        <div className="flex items-center gap-2.5">
          <span className="w-9 h-9 rounded-xl flex items-center justify-center border border-white/10 bg-white/[0.03]">
            <ModalityIcon className="w-4.5 h-4.5 text-white/70" />
          </span>
          <h3 className="text-sm font-bold tracking-tight text-white/90">{heading}</h3>
        </div>
        <span
          className="flex items-center gap-1.5 text-xs font-semibold tracking-wide fc-text-muted px-2.5 py-1 rounded-full border border-white/10 bg-white/[0.03]"
          title={
            isRemote
              ? "Described by the cloud multimodal model"
              : "Described on-device — orientation only, not a court-grade reading"
          }
        >
          {isRemote ? <Sparkles className="w-3.5 h-3.5" /> : <Cpu className="w-3.5 h-3.5" />}
          {isRemote ? remoteLabel : "On-device read"}
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

      {hasDetails && (
        <div className="mt-3.5 pt-3.5 border-t border-white/[0.06]">
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            className="flex items-center gap-1.5 text-xs font-semibold tracking-wide fc-text-muted hover:text-white/80 transition-colors"
          >
            <ChevronDown
              className={clsx("w-3.5 h-3.5 transition-transform", open && "rotate-180")}
            />
            {open ? "Hide full evidence context" : "Show full evidence context"}
          </button>

          {open && (
            <dl className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3">
              {integrityRead && (
                <div className="sm:col-span-2">
                  <dt className="text-[11px] font-semibold uppercase tracking-wider fc-text-muted mb-1">
                    Holistic integrity read
                  </dt>
                  <dd className="text-sm fc-text-secondary">{integrityRead}</dd>
                </div>
              )}
              {presentGroups.map((g) => {
                const items = (details?.[g.key] as string[]) ?? [];
                const isText = g.kind === "text";
                const isAlert = g.kind === "alert";
                return (
                  <div key={g.key} className={clsx(isText && "sm:col-span-2")}>
                    <dt
                      className={clsx(
                        "text-[11px] font-semibold uppercase tracking-wider mb-1.5",
                        isAlert ? "text-amber-300/80" : "fc-text-muted",
                      )}
                    >
                      {g.label}
                    </dt>
                    <dd>
                      {isText ? (
                        <ul className="space-y-1">
                          {items.map((it, i) => (
                            <li key={i} className="text-sm fc-text-secondary leading-relaxed">
                              {cleanFindingText(it)}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <div className="flex flex-wrap gap-1.5">
                          {items.map((it, i) => (
                            <span
                              key={i}
                              className={clsx(
                                "text-xs px-2 py-0.5 rounded-md border",
                                isAlert
                                  ? "border-amber-400/20 bg-amber-400/[0.06] text-amber-200/90"
                                  : "border-white/10 bg-white/[0.04] fc-text-secondary",
                              )}
                            >
                              {it}
                            </span>
                          ))}
                        </div>
                      )}
                    </dd>
                  </div>
                );
              })}
            </dl>
          )}
        </div>
      )}
    </div>
  );
}
