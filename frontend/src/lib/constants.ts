import {
  Image as ImageIcon,
  Mic,
  Crosshair,
  Video,
  FileCode2,
  Scale,
  UploadCloud,
  Cpu,
  FileSignature,
  FileImage,
  FileText,
  FileAudio,
  FileVideo,
} from "lucide-react";

export const AGENTS = [
  {
    id: "AGT-01",
    name: "Image Forensics",
    icon: ImageIcon,
    color: "#22d3ee",
    bgRgb: "34,211,238",
    badge: "Visual Authenticity",
    desc: "ELA analysis, copy-move detection, PRNU camera noise fingerprints to expose visual splicing and region tampering.",
  },
  {
    id: "AGT-02",
    name: "Audio Forensics",
    icon: Mic,
    color: "#818cf8",
    bgRgb: "129,140,248",
    badge: "Acoustic Integrity",
    desc: "Wav2Vec2 deepfake detection and spectral analysis to catch voice cloning, audio splicing, and synthesis artefacts.",
  },
  {
    id: "AGT-03",
    name: "Object Detection",
    icon: Crosshair,
    color: "#38bdf8",
    bgRgb: "56,189,248",
    badge: "Contextual Analysis",
    desc: "YOLOv8 lighting, shadow, and reflection anomaly detection to spot compositing errors and contextual inconsistencies.",
  },
  {
    id: "AGT-04",
    name: "Video Forensics",
    icon: Video,
    color: "#2dd4bf",
    bgRgb: "45,212,191",
    badge: "Temporal Analysis",
    desc: "Frame-by-frame face-swap detection and temporal inconsistency scans across the full video timeline.",
  },
  {
    id: "AGT-05",
    name: "Metadata Expert",
    icon: FileCode2,
    color: "#60a5fa",
    bgRgb: "96,165,250",
    badge: "Digital Footprint",
    desc: "EXIF/XMP extraction, GPS cross-reference, solar positioning checks, and device fingerprinting.",
  },
  {
    id: "AGT-06",
    name: "Council Arbiter",
    icon: Scale,
    color: "#e2b94a",
    bgRgb: "226,185,74",
    badge: "Final Synthesis",
    desc: "Cross-references all agent findings, resolves conflicts, and synthesises a unified ECDSA P-256 signed verdict.",
  },
] as const;

export const AGENTS_DATA = AGENTS;

export const ALLOWED_MIME_TYPES = new Set([
  "image/jpeg",
  "image/png",
  "image/tiff",
  "image/webp",
  "image/gif",
  "image/bmp",
  "video/mp4",
  "video/quicktime",
  "video/x-msvideo",
  "video/x-matroska",
  "audio/wav",
  "audio/mpeg",
  "audio/mp3",
  "audio/mp4",
  "audio/x-wav",
  "application/pdf",
  "text/plain",
  "text/csv",
  "application/json",
]);

export const HOW_IT_WORKS = [
  {
    step: "01",
    icon: UploadCloud,
    title: "Secure Ingestion",
    desc: "File uploaded over TLS. SHA-256 hash calculated immediately to establish an immutable chain of custody.",
    tag: "Chain of Custody",
    color: "#22d3ee",
    rgb: "34,211,238",
  },
  {
    step: "02",
    icon: Cpu,
    title: "Multi-Agent Scan",
    desc: "Five specialist agents run parallel deep analysis on image, audio, video, and metadata evidence.",
    tag: "5 Agents Active",
    color: "#818cf8",
    rgb: "129,140,248",
  },
  {
    step: "03",
    icon: Scale,
    title: "Council Deliberation",
    desc: "The Arbiter cross-references all agent findings, resolves conflicts, and synthesises a unified confidence score.",
    tag: "Arbiter Review",
    color: "#f59e0b",
    rgb: "245,158,11",
  },
  {
    step: "04",
    icon: FileSignature,
    title: "Cryptographic Verdict",
    desc: "Tamper-evident ECDSA P-256 signed forensic report — court-admissible and permanently immutable.",
    tag: "Verdict Signed",
    color: "#34d399",
    rgb: "52,211,153",
  },
] as const;

export const REPORT_TABS = ["Image", "Text", "Audio", "Video"] as const;
export type ReportTab = (typeof REPORT_TABS)[number];

export const TAB_ICONS: Record<ReportTab, typeof FileImage> = {
  Image: FileImage,
  Text: FileText,
  Audio: FileAudio,
  Video: FileVideo,
};


