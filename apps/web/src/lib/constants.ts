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
    desc: "Analyzes images to detect signs of AI generation, photoshopping, or hidden tampering in specific regions.",
  },
  {
    id: "Agent2",
    name: "Audio Forensics",
    icon: Mic,
    color: "#0891b2",
    bgRgb: "8,145,178",
    badge: "Acoustic Integrity",
    desc: "Examines audio files to catch deepfake voices, AI voice cloning, and unnatural speech patterns.",
  },
  {
    id: "Agent3",
    name: "Object Detection",
    icon: Crosshair,
    color: "#06b6d4",
    bgRgb: "6,182,212",
    badge: "Contextual Analysis",
    desc: "Scans scenes to find inconsistent lighting, objects that don't belong, and contextual errors.",
  },
  {
    id: "Agent4",
    name: "Video Forensics",
    icon: Video,
    color: "#10b981",
    bgRgb: "16,185,129",
    badge: "Temporal Analysis",
    desc: "Checks videos frame-by-frame to uncover face-swaps, deepfakes, and manipulated movements.",
  },
  {
    id: "Agent5",
    name: "Metadata Expert",
    icon: FileCode2,
    color: "#0891b2",
    bgRgb: "8,145,178",
    badge: "Digital Footprint",
    desc: "Inspects hidden file data to verify where, when, and how the evidence was originally created.",
  },
  {
    id: "AGT-06",
    name: "Council Arbiter",
    icon: Scale,
    color: "#10b981",
    bgRgb: "16,185,129",
    badge: "Final Synthesis",
    desc: "Reviews the findings from all agents to make a final, secure, and definitive judgment on authenticity.",
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
    desc: "Your files are uploaded securely. We immediately lock them down to guarantee they remain untampered.",
    tag: "Chain of Custody",
    color: "#0891b2",
    rgb: "8,145,178",
  },
  {
    step: "02",
    icon: Cpu,
    title: "Multi-Agent Scan",
    desc: "Our specialized AI agents work together to deeply analyze your images, audio, video, and hidden data.",
    tag: "5 Agents Active",
    color: "#06b6d4",
    rgb: "6,182,212",
  },
  {
    step: "03",
    icon: Scale,
    title: "Council Deliberation",
    desc: "The agents share their findings with the Arbiter, who weighs all the evidence to reach a final conclusion.",
    tag: "Arbiter Review",
    color: "#10b981",
    rgb: "16,185,129",
  },
  {
    step: "04",
    icon: FileSignature,
    title: "Cryptographic Verdict",
    desc: "You receive a fully secured, tamper-proof forensic report that clearly explains the final results.",
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

// perceived responsiveness for analyses that typically complete in 15–90 s.
export const ARBITER_POLL_INTERVAL_MS = 2_500;

// Maximum arbiter polling attempts before declaring a timeout.
// 720 × 2.5 s = 30 minutes — enough headroom for deep video analysis.
export const ARBITER_POLL_MAX_ATTEMPTS = 720;

// 30 s permits 50MB uploads and slow Redis/Docker cold starts without timing out.
export const INVESTIGATION_REQUEST_TIMEOUT_MS = 30_000;
