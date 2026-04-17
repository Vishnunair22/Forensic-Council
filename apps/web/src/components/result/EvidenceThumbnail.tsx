"use client";

import { Image as ImageIcon, Film, Mic, FileText } from "lucide-react";

interface EvidenceThumbnailProps {
 thumbnail?: string | null;
 mimeType?: string | null;
 fileName?: string;
 /** Extra className on the outer container */
 className?: string;
}

function mimeCategory(mime?: string | null): "image" | "video" | "audio" | "doc" {
 if (!mime) return "doc";
 if (mime.startsWith("image/")) return "image";
 if (mime.startsWith("video/")) return "video";
 if (mime.startsWith("audio/")) return "audio";
 return "doc";
}

const CATEGORY_ICON = {
 image: ImageIcon,
 video: Film,
 audio: Mic,
 doc: FileText,
} as const;

const CATEGORY_COLOR: Record<string, string> = {
 image: "#22d3ee",
 video: "#2dd4bf",
 audio: "#818cf8",
 doc: "#60a5fa",
};

export function EvidenceThumbnail({
 thumbnail,
 mimeType,
 fileName,
 className = "",
}: EvidenceThumbnailProps) {
 const cat = mimeCategory(mimeType);
 const Icon = CATEGORY_ICON[cat];
 const color = CATEGORY_COLOR[cat];

 const label = fileName
  ? `Evidence file: ${fileName}`
  : `Evidence ${cat} file`;

 return (
  <div
   className={`relative overflow-hidden rounded-2xl border border-white/[0.06] bg-white/[0.02] flex items-center justify-center ${className}`}
   style={{ aspectRatio: "16/9" }}
   role="img"
   aria-label={label}
  >
   {thumbnail && cat === "image" ? (
    /* eslint-disable-next-line @next/next/no-img-element */
    <img
     src={thumbnail}
     alt={label}
     className="w-full h-full object-cover"
     loading="lazy"
     decoding="async"
    />
   ) : thumbnail && cat === "video" ? (
    /* eslint-disable-next-line @next/next/no-img-element */
    <img
     src={thumbnail}
     alt={`Video thumbnail — ${label}`}
     className="w-full h-full object-cover"
     loading="lazy"
     decoding="async"
    />
   ) : (
    <div className="flex flex-col items-center justify-center gap-3 p-6 text-center">
     <div
      className="w-14 h-14 rounded-2xl flex items-center justify-center border"
      style={{
       background: `rgba(${cat === "image" ? "34,211,238" : cat === "video" ? "45,212,191" : cat === "audio" ? "129,140,248" : "96,165,250"},0.12)`,
       borderColor: `${color}30`,
      }}
     >
      <Icon className="w-7 h-7" style={{ color }} aria-hidden="true" />
     </div>
     <span className="text-[10px] font-mono font-bold tracking-widest text-white/50">
      {cat} evidence
     </span>
     {fileName && (
      <span className="text-[11px] text-white/40 truncate max-w-[140px]">
       {fileName}
      </span>
     )}
    </div>
   )}

   {/* Overlay gradient for non-image types with thumbnail */}
   {thumbnail && cat !== "image" && cat !== "video" && (
    <div className="absolute inset-0 bg-gradient-to-t from-black/50 to-transparent pointer-events-none" />
   )}
  </div>
 );
}
