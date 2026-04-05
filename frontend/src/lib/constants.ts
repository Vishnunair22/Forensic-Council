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

export const MOCK_REPORTS: Record<
  ReportTab,
  {
    file: string;
    verdict: string;
    verdictLabel: string;
    confidence: number;
    agents: { name: string; verdict: string; conf: number; finding: string }[];
    arbiterNote: string;
  }
> = {
  Image: {
    file: "evidence_photo_2024.jpg",
    verdict: "MANIPULATED",
    verdictLabel: "Manipulation Detected",
    confidence: 91,
    agents: [
      {
        name: "Image Forensics",
        verdict: "SUSPICIOUS",
        conf: 94,
        finding:
          "ELA heatmap reveals region-inconsistent JPEG compression in top-right sky quadrant.",
      },
      {
        name: "Object & Weapon Analyst",
        verdict: "SUSPICIOUS",
        conf: 87,
        finding:
          "Shadow direction inconsistency at 14\u00b0 offset from main subject.",
      },
      {
        name: "Metadata Expert",
        verdict: "SUSPICIOUS",
        conf: 78,
        finding: "Camera model inconsistent with embedded ICC color profile.",
      },
      {
        name: "Audio Forensics",
        verdict: "NOT_APPLICABLE",
        conf: 0,
        finding: "File type not applicable for audio analysis.",
      },
      {
        name: "Video Forensics",
        verdict: "NOT_APPLICABLE",
        conf: 0,
        finding: "File type not applicable for video analysis.",
      },
    ],
    arbiterNote: "Three independent agents corroborate manipulative artefacts.",
  },
  Text: {
    file: "document_verification.pdf",
    verdict: "AUTHENTIC",
    verdictLabel: "Authentic",
    confidence: 95,
    agents: [
      {
        name: "Text Analysis",
        verdict: "AUTHENTIC",
        conf: 98,
        finding: "No anomalies detected in document structure.",
      },
      {
        name: "Metadata Expert",
        verdict: "AUTHENTIC",
        conf: 92,
        finding: "Document timestamps consistent with claimed origin.",
      },
      {
        name: "Image Forensics",
        verdict: "NOT_APPLICABLE",
        conf: 0,
        finding: "File type not applicable for image analysis.",
      },
      {
        name: "Audio Forensics",
        verdict: "NOT_APPLICABLE",
        conf: 0,
        finding: "File type not applicable for audio analysis.",
      },
      {
        name: "Video Forensics",
        verdict: "NOT_APPLICABLE",
        conf: 0,
        finding: "File type not applicable for video analysis.",
      },
    ],
    arbiterNote:
      "Text analysis confirms authenticity across all applicable metrics.",
  },
  Audio: {
    file: "voice_recording.wav",
    verdict: "LIKELY_MANIPULATED",
    verdictLabel: "Likely Manipulated",
    confidence: 78,
    agents: [
      {
        name: "Audio Forensics",
        verdict: "SUSPICIOUS",
        conf: 82,
        finding: "Wav2Vec2 deepfake classifier: 82% confidence.",
      },
      {
        name: "Metadata Expert",
        verdict: "SUSPICIOUS",
        conf: 71,
        finding:
          "Editing software metadata inconsistent with claimed field recording.",
      },
      {
        name: "Image Forensics",
        verdict: "NOT_APPLICABLE",
        conf: 0,
        finding: "File type not applicable for image analysis.",
      },
      {
        name: "Object & Weapon Analyst",
        verdict: "NOT_APPLICABLE",
        conf: 0,
        finding: "File type not applicable for object analysis.",
      },
      {
        name: "Video Forensics",
        verdict: "NOT_APPLICABLE",
        conf: 0,
        finding: "File type not applicable for video analysis.",
      },
    ],
    arbiterNote:
      "Audio synthesis artefacts are consistent across acoustic and metadata analysis.",
  },
  Video: {
    file: "security_footage.mp4",
    verdict: "AUTHENTIC",
    verdictLabel: "Authentic",
    confidence: 88,
    agents: [
      {
        name: "Video Forensics",
        verdict: "AUTHENTIC",
        conf: 90,
        finding: "No face-swap artefacts across 3,241 frames.",
      },
      {
        name: "Image Forensics",
        verdict: "AUTHENTIC",
        conf: 86,
        finding: "Per-keyframe ELA analysis shows uniform JPEG compression.",
      },
      {
        name: "Object & Weapon Analyst",
        verdict: "AUTHENTIC",
        conf: 84,
        finding: "Lighting direction and shadow consistency validated.",
      },
      {
        name: "Metadata Expert",
        verdict: "AUTHENTIC",
        conf: 91,
        finding: "Device fingerprint matches claimed camera model.",
      },
      {
        name: "Audio Forensics",
        verdict: "AUTHENTIC",
        conf: 83,
        finding: "No synthetic speech artefacts in embedded audio track.",
      },
    ],
    arbiterNote:
      "All five agents converge on authentic. No evidence of manipulation found.",
  },
};
