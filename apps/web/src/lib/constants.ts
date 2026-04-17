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
    id: "Agent1",
    name: "Image Forensics",
    icon: ImageIcon,
    color: "#06b6d4",
    bgRgb: "6,182,212",
    badge: "Visual Authenticity",
    desc: "SigLIP 2 scene grounding, BusterNet copy-move, and TruFor ViT-based splicing detection to expose AI-region tampering.",
  },
  {
    id: "Agent2",
    name: "Audio Forensics",
    icon: Mic,
    color: "#0891b2",
    bgRgb: "8,145,178",
    badge: "Acoustic Integrity",
    desc: "Wav2Vec2 neural prosody and AASIST anti-spoofing to catch voice cloning and AI speech synthesis.",
  },
  {
    id: "Agent3",
    name: "Object Detection",
    icon: Crosshair,
    color: "#06b6d4",
    bgRgb: "6,182,212",
    badge: "Contextual Analysis",
    desc: "YOLO11 object detection, lighting correlation, and vector contraband search for scene-level inconsistences.",
  },
  {
    id: "Agent4",
    name: "Video Forensics",
    icon: Video,
    color: "#10b981",
    bgRgb: "16,185,129",
    badge: "Temporal Analysis",
    desc: "VFI Error Mapping and frame-level face-swap detection across the full forensic timeline.",
  },
  {
    id: "Agent5",
    name: "Metadata Expert",
    icon: FileCode2,
    color: "#0891b2",
    bgRgb: "8,145,178",
    badge: "Digital Footprint",
    desc: "EXIF Isolation Forest anomalies, Astro Grounding, and C2PA provenance verification.",
  },
  {
    id: "AGT-06",
    name: "Council Arbiter",
    icon: Scale,
    color: "#10b981",
    bgRgb: "16,185,129",
    badge: "Final Synthesis",
    desc: "Cross-references all agent findings, resolves conflicts, and synthesises a unified ECDSA P-256 signed verdict.",
  },
] as const;

export const ALLOWED_MIME_TYPES = new Set([
  // Images
  "image/jpeg",
  "image/png",
  "image/tiff",
  "image/webp",
  "image/gif",
  "image/bmp",
  // Video
  "video/mp4",
  "video/quicktime",
  "video/x-msvideo",
  // Audio
  "audio/wav",
  "audio/x-wav",
  "audio/mpeg",
  "audio/mp4",
  "audio/flac",
]);

export const HOW_IT_WORKS = [
  {
    step: "01",
    icon: UploadCloud,
    title: "Secure Ingestion",
    desc: "File uploaded over TLS. SHA-256 hash calculated immediately to establish an immutable chain of custody.",
    tag: "Chain of Custody",
    color: "#0891b2",
    rgb: "8,145,178",
  },
  {
    step: "02",
    icon: Cpu,
    title: "Multi-Agent Scan",
    desc: "Five specialist agents run parallel deep analysis on image, audio, video, and metadata evidence.",
    tag: "5 Agents Active",
    color: "#06b6d4",
    rgb: "6,182,212",
  },
  {
    step: "03",
    icon: Scale,
    title: "Council Deliberation",
    desc: "The Arbiter cross-references all agent findings, resolves conflicts, and synthesises a unified confidence score.",
    tag: "Arbiter Review",
    color: "#10b981",
    rgb: "16,185,129",
  },
  {
    step: "04",
    icon: FileSignature,
    title: "Cryptographic Verdict",
    desc: "Tamper-evident ECDSA P-256 signed forensic report — court-admissible and permanently immutable.",
    tag: "Verdict Signed",
    color: "#10b981",
    rgb: "16,185,129",
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

// ── Polling Intervals ─────────────────────────────────────────────────────────
// Arbiter status polling on the result page. 2.5 s balances server load vs.
// perceived responsiveness for analyses that typically complete in 15–90 s.
export const ARBITER_POLL_INTERVAL_MS = 2_500;

// Maximum arbiter polling attempts before declaring a timeout.
// 720 × 2.5 s = 30 minutes — enough headroom for deep video analysis.
export const ARBITER_POLL_MAX_ATTEMPTS = 720;

// 30 s permits 50MB uploads and slow Redis/Docker cold starts without timing out.
export const INVESTIGATION_REQUEST_TIMEOUT_MS = 30_000;
