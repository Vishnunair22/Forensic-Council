"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence, useScroll, useTransform, useMotionValue, useSpring } from "framer-motion";
import {
  ArrowRight, UploadCloud, X, RefreshCw,
  FileImage, FileAudio, FileVideo, FileText,
  Image as ImageIcon, Mic, Crosshair, Video, FileCode2, Scale,
  ShieldCheck, Cpu, FileSignature, CheckCircle, AlertTriangle,
} from "lucide-react";
import { autoLoginAsInvestigator } from "@/lib/api";
import { GlobalFooter } from "@/components/ui/GlobalFooter";

// ── Agent data ────────────────────────────────────────────────────────────────
const AGENTS = [
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
    color: "#a78bfa",
    bgRgb: "167,139,250",
    badge: "Acoustic Integrity",
    desc: "Wav2Vec2 deepfake detection and spectral analysis to catch voice cloning, audio splicing, and synthesis artefacts.",
  },
  {
    id: "AGT-03",
    name: "Object Detection",
    icon: Crosshair,
    color: "#f59e0b",
    bgRgb: "245,158,11",
    badge: "Contextual Analysis",
    desc: "YOLOv8 lighting, shadow, and reflection anomaly detection to spot compositing errors and contextual inconsistencies.",
  },
  {
    id: "AGT-04",
    name: "Video Forensics",
    icon: Video,
    color: "#f43f5e",
    bgRgb: "244,63,94",
    badge: "Temporal Analysis",
    desc: "Frame-by-frame face-swap detection and temporal inconsistency scans across the full video timeline.",
  },
  {
    id: "AGT-05",
    name: "Metadata Expert",
    icon: FileCode2,
    color: "#34d399",
    bgRgb: "52,211,153",
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

// ── How It Works data ─────────────────────────────────────────────────────────
const HOW_IT_WORKS = [
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
    color: "#a78bfa",
    rgb: "167,139,250",
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

// ── Mock report data for Example Report section ───────────────────────────────
const REPORT_TABS = ["Image", "Text", "Audio", "Video"] as const;
type ReportTab = (typeof REPORT_TABS)[number];

const TAB_ICONS: Record<ReportTab, typeof FileImage> = {
  Image: FileImage,
  Text: FileText,
  Audio: FileAudio,
  Video: FileVideo,
};

const MOCK_REPORTS: Record<ReportTab, {
  file: string;
  verdict: string;
  verdictLabel: string;
  confidence: number;
  agents: { name: string; verdict: string; conf: number; finding: string }[];
  arbiterNote: string;
}> = {
  "Image": {
    file: "evidence_photo_2024.jpg",
    verdict: "MANIPULATED",
    verdictLabel: "Manipulation Detected",
    confidence: 91,
    agents: [
      { name: "Image Forensics", verdict: "SUSPICIOUS", conf: 94, finding: "ELA heatmap reveals region-inconsistent JPEG compression in top-right sky quadrant. Copy-move detection confirmed 3 cloned patches at 98% correlation." },
      { name: "Object & Weapon Analyst", verdict: "SUSPICIOUS", conf: 87, finding: "Shadow direction inconsistency at 14° offset from main subject. Lighting frequency mismatch detected in foreground object." },
      { name: "Metadata Expert", verdict: "SUSPICIOUS", conf: 78, finding: "Camera model (Canon EOS R5) inconsistent with embedded ICC color profile. GPS timestamp contradicts reported location by 2,340 km." },
      { name: "Audio Forensics", verdict: "NOT_APPLICABLE", conf: 0, finding: "File type not applicable for audio analysis." },
      { name: "Video Forensics", verdict: "NOT_APPLICABLE", conf: 0, finding: "File type not applicable for video analysis." },
    ],
    arbiterNote: "Three independent agents corroborate manipulative artefacts. The geospatial contradiction and lighting inconsistency are independent vectors — convergent signals confirm tampering.",
  },
  "Text": {
    file: "document_verification.pdf",
    verdict: "AUTHENTIC",
    verdictLabel: "Authentic",
    confidence: 95,
    agents: [
      { name: "Text Analysis", verdict: "AUTHENTIC", conf: 98, finding: "No anomalies detected in document structure. Metadata confirms document was created using standard word processing software." },
      { name: "Metadata Expert", verdict: "AUTHENTIC", conf: 92, finding: "Document timestamps, author information, and edit history are consistent with claimed origin." },
      { name: "Image Forensics", verdict: "NOT_APPLICABLE", conf: 0, finding: "File type not applicable for image analysis." },
      { name: "Audio Forensics", verdict: "NOT_APPLICABLE", conf: 0, finding: "File type not applicable for audio analysis." },
      { name: "Video Forensics", verdict: "NOT_APPLICABLE", conf: 0, finding: "File type not applicable for video analysis." },
    ],
    arbiterNote: "Text analysis confirms authenticity across all applicable metrics.",
  },
  "Audio": {
    file: "voice_recording.wav",
    verdict: "LIKELY_MANIPULATED",
    verdictLabel: "Likely Manipulated",
    confidence: 78,
    agents: [
      { name: "Audio Forensics", verdict: "SUSPICIOUS", conf: 82, finding: "Wav2Vec2 deepfake classifier: 82% confidence. Spectral gap at 4.2–6.8 kHz band is characteristic of voice synthesis artefacts." },
      { name: "Metadata Expert", verdict: "SUSPICIOUS", conf: 71, finding: "Editing software metadata (Adobe Audition 23.3) inconsistent with claimed field recording device. Edit history markers detected." },
      { name: "Image Forensics", verdict: "NOT_APPLICABLE", conf: 0, finding: "File type not applicable for image analysis." },
      { name: "Object & Weapon Analyst", verdict: "NOT_APPLICABLE", conf: 0, finding: "File type not applicable for object analysis." },
      { name: "Video Forensics", verdict: "NOT_APPLICABLE", conf: 0, finding: "File type not applicable for video analysis." },
    ],
    arbiterNote: "Audio synthesis artefacts are consistent across both acoustic and metadata analysis. Confidence meets the threshold for 'Likely Manipulated'. Manual expert review recommended.",
  },
  "Video": {
    file: "security_footage.mp4",
    verdict: "AUTHENTIC",
    verdictLabel: "Authentic",
    confidence: 88,
    agents: [
      { name: "Video Forensics", verdict: "AUTHENTIC", conf: 90, finding: "No face-swap artefacts across 3,241 frames. Temporal consistency score: 0.94. No dropped or duplicated keyframes detected." },
      { name: "Image Forensics", verdict: "AUTHENTIC", conf: 86, finding: "Per-keyframe ELA analysis shows uniform JPEG compression throughout. No region inconsistencies found." },
      { name: "Object & Weapon Analyst", verdict: "AUTHENTIC", conf: 84, finding: "Lighting direction and shadow consistency validated across 12 tracked objects. No compositing errors detected." },
      { name: "Metadata Expert", verdict: "AUTHENTIC", conf: 91, finding: "Device fingerprint matches claimed camera model. GPS track consistent with facility coordinates. No edit markers present." },
      { name: "Audio Forensics", verdict: "AUTHENTIC", conf: 83, finding: "No synthetic speech artefacts in embedded audio track. Ambient noise profile matches environmental signature." },
    ],
    arbiterNote: "All five agents converge on authentic. Temporal, spatial, and acoustic signals are internally consistent across independent analysis vectors. No evidence of manipulation found.",
  },
};



// ── Upload Modal ──────────────────────────────────────────────────────────────
function UploadModal({ onClose, onFileSelected }: { onClose: () => void; onFileSelected: (f: File) => void }) {
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback((f: File) => { onFileSelected(f); }, [onFileSelected]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  }, [handleFile]);

  return (
    <motion.div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4 backdrop-blur-md"
      style={{ background: "rgba(0,0,0,0.6)" }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onClose}
    >
      <motion.div
        className="glass-modal relative w-full max-w-lg rounded-3xl p-10 overflow-hidden"
        initial={{ scale: 0.9, opacity: 0, y: 20 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.9, opacity: 0, y: 20 }}
        transition={{ type: "spring", damping: 25, stiffness: 300 }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Animated background flare */}
        <div className="absolute -top-24 -right-24 w-48 h-48 bg-cyan-500/10 blur-[80px] pointer-events-none" />
        
        <button
          onClick={onClose}
          className="absolute top-6 right-6 p-2 rounded-xl cursor-pointer hover:bg-white/5 transition-colors border border-white/5"
          aria-label="Close upload modal"
        >
          <X className="w-5 h-5 text-white/40" />
        </button>

        <div className="relative z-10">
          <div className="mb-8">
            <h3 className="text-2xl font-bold text-white tracking-tight">Upload Evidence</h3>
          </div>

          <div
            className="group relative rounded-2xl border-2 border-dashed p-12 text-center cursor-pointer transition-all duration-300 overflow-hidden"
            style={{
              borderColor: isDragging ? "rgba(34,211,238,0.5)" : "rgba(255,255,255,0.08)",
              background: isDragging ? "rgba(34,211,238,0.05)" : "rgba(255,255,255,0.02)",
            }}
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            {/* Hover glow */}
            <div className="absolute inset-0 bg-gradient-to-b from-cyan-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
            
            <div className="relative z-10">
              <div className="w-16 h-16 rounded-2xl bg-cyan-500/10 flex items-center justify-center mx-auto mb-5 border border-cyan-500/20 group-hover:scale-110 transition-transform duration-300">
                <UploadCloud className="w-8 h-8 text-cyan-400" />
              </div>
              <p className="text-lg font-semibold text-white mb-2">
                Drop file here or <span className="text-cyan-400 underline underline-offset-4 decoration-cyan-400/30">browse</span>
              </p>
              <div className="flex items-center justify-center gap-3 opacity-40">
                <FileImage className="w-4 h-4" />
                <FileVideo className="w-4 h-4" />
                <FileAudio className="w-4 h-4" />
                <FileText className="w-4 h-4" />
              </div>
            </div>

            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              accept="image/*,audio/*,video/*"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
            />
          </div>

          <div className="mt-8 flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-500" />
              <p className="text-sm font-medium text-white/60">Supported: Image, Video, Audio, Document</p>
            </div>
            <p className="text-xs text-white/30 ml-3.5">
              Maximum file size: 50 MB • SHA-256 integrity check performed automatically.
            </p>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}

function UploadSuccessModal({ file, onNewUpload, onStartAnalysis }: {
  file: File;
  onNewUpload: () => void;
  onStartAnalysis: () => void;
}) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      return;
    }

    const isMedia = file.type.startsWith("image/") || 
                    file.type.startsWith("video/") || 
                    /\.(jpe?g|png|gif|bmp|webp|jfif|mp4|webm|mov|ogg)$/i.test(file.name);
    
    if (isMedia) {
      const reader = new FileReader();
      reader.onloadend = () => setPreviewUrl(reader.result as string);
      reader.onerror = () => setHasError(true);
      reader.readAsDataURL(file);
    } else {
      setPreviewUrl(null);
    }
  }, [file]);

  const isVideo = file.type.startsWith("video/") || /\.(mp4|webm|mov|ogg)$/i.test(file.name);
  const FileTypeIcon = file.type.startsWith("image/") ? FileImage
    : file.type.startsWith("audio/") ? FileAudio
    : isVideo ? FileVideo
    : FileText;

  return (
    <motion.div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4 backdrop-blur-xl"
      style={{ background: "rgba(0,0,0,0.8)" }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <motion.div
        className="glass-modal relative w-full max-w-sm rounded-[2rem] p-10 text-center overflow-hidden border border-white/20 shadow-[0_32px_120px_rgba(0,0,0,0.9)]"
        initial={{ scale: 0.9, opacity: 0, y: 20 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.9, opacity: 0, y: 20 }}
        transition={{ type: "spring", damping: 25, stiffness: 300 }}
      >
        {/* Background glow accent */}
        <div className="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-transparent via-cyan-500/50 to-transparent opacity-50" />
        <div className="absolute -top-32 -left-32 w-64 h-64 bg-cyan-500/20 blur-[100px] pointer-events-none" />

        <div
          className="w-32 h-32 rounded-3xl mx-auto mb-8 overflow-hidden flex items-center justify-center relative z-10 border border-white/10 shadow-2xl bg-black/20"
        >
          {previewUrl && !hasError ? (
            isVideo ? (
              <video key={previewUrl} src={previewUrl} className="w-full h-full object-cover" muted loop autoPlay playsInline onError={() => setHasError(true)} />
            ) : (
              <img key={previewUrl} src={previewUrl} alt="File preview" className="w-full h-full object-cover" onError={() => setHasError(true)} />
            )
          ) : (
            <div className="flex flex-col items-center gap-2">
              <FileTypeIcon className="w-12 h-12 text-cyan-400/60" aria-hidden="true" />
              <span className="text-[10px] font-mono text-cyan-400/40 uppercase tracking-widest">NO PREVIEW</span>
            </div>
          )}
        </div>

        <div className="relative z-10">
          <div className="flex flex-col items-center mb-10">
            <div className="inline-flex items-center gap-2 mb-4 bg-emerald-500/20 px-4 py-1.5 rounded-full border border-emerald-500/30">
              <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_8px_rgba(52,211,153,0.5)]" />
              <span className="text-[11px] font-extrabold text-emerald-400 tracking-wider uppercase">Evidence Ready</span>
            </div>
            <h3 className="text-white text-xl font-extrabold truncate max-w-full px-2 mb-2 leading-tight">{file.name}</h3>
            <div className="flex items-center gap-3 text-[11px] font-mono text-white/40 uppercase tracking-widest">
              <span>{file.type.split('/')[1] || "BINARY"}</span>
              <span className="w-1 h-1 rounded-full bg-white/20" />
              <span>{(file.size / (1024 * 1024)).toFixed(2)} MB</span>
            </div>
          </div>

          <div className="flex gap-4">
            <motion.button
              onClick={onNewUpload}
              whileHover={{ scale: 1.05, background: "rgba(255,255,255,0.12)", borderColor: "rgba(255,255,255,0.3)" }}
              whileTap={{ scale: 0.95 }}
              className="flex-1 py-4 rounded-2xl text-xs font-bold cursor-pointer transition-all border border-white/10 text-white/80 flex items-center justify-center gap-2"
              style={{ background: "rgba(255,255,255,0.06)" }}
            >
              <RefreshCw className="w-4 h-4" />
              Reset
            </motion.button>

            <motion.button
              onClick={onStartAnalysis}
              whileHover={{ scale: 1.05, boxShadow: "0 0 50px rgba(34,211,238,0.5)", filter: "brightness(1.1)" }}
              whileTap={{ scale: 0.95 }}
              className="flex-[1.5] py-4 rounded-2xl text-base font-extrabold cursor-pointer transition-all text-white flex items-center justify-center gap-2 shadow-[0_12px_40px_rgba(34,211,238,0.3)]"
              style={{
                background: "linear-gradient(135deg, #06b6d4 0%, #22d3ee 100%)",
              }}
            >
              Analyse
              <ArrowRight className="w-5 h-5" />
            </motion.button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}

// ── Example Report ────────────────────────────────────────────────────────────
function ExampleReportSection() {
  const [activeTab, setActiveTab] = useState(0);
  const tabKey = REPORT_TABS[activeTab];
  const report = MOCK_REPORTS[tabKey];

  const vcColor = (v: string) => {
    const u = v.toUpperCase();
    if (u.includes("MANIPULAT")) return { color: "#f43f5e", bg: "rgba(244,63,94,0.07)", border: "rgba(244,63,94,0.18)", Icon: AlertTriangle };
    if (u.includes("AUTHENTIC")) return { color: "#34d399", bg: "rgba(52,211,153,0.07)", border: "rgba(52,211,153,0.18)", Icon: CheckCircle };
    return { color: "#f59e0b", bg: "rgba(245,158,11,0.07)", border: "rgba(245,158,11,0.18)", Icon: AlertTriangle };
  };

  const vc = vcColor(report.verdict);

  return (
    <div className="w-full max-w-4xl mx-auto">
      {/* Tabs */}
      <div className="flex gap-2 mb-6 flex-wrap">
        {REPORT_TABS.map((tab, i) => {
          const TabIcon = TAB_ICONS[tab];
          return (
            <button
              key={tab}
              onClick={() => setActiveTab(i)}
              className="px-5 py-2 rounded-xl text-sm font-medium cursor-pointer transition-all flex items-center gap-2"
              style={activeTab === i ? {
                background: "rgba(34,211,238,0.1)",
                border: "1px solid rgba(34,211,238,0.25)",
                color: "#22d3ee",
              } : {
                background: "rgba(255,255,255,0.03)",
                border: "1px solid rgba(255,255,255,0.06)",
                color: "rgba(255,255,255,0.4)",
              }}
            >
              <TabIcon className="w-4 h-4" aria-hidden="true" />
              {tab}
            </button>
          );
        })}
      </div>

      {/* Report card */}
      <motion.div
        key={activeTab}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="rounded-2xl overflow-hidden"
        style={{
          background: "rgba(255,255,255,0.03)",
          backdropFilter: "blur(24px)",
          WebkitBackdropFilter: "blur(24px)",
          border: "1px solid rgba(255,255,255,0.07)",
          boxShadow: "inset 0 1px 0 rgba(255,255,255,0.06)",
        }}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b flex items-center justify-between" style={{ borderColor: "rgba(255,255,255,0.05)" }}>
          <div className="flex items-center gap-2.5">
            <ShieldCheck className="w-4 h-4" style={{ color: "rgba(34,211,238,0.5)" }} aria-hidden="true" />
            <span className="text-xs font-mono tracking-widest" style={{ color: "rgba(255,255,255,0.3)" }}>FORENSIC COUNCIL</span>
          </div>
          <span className="text-xs font-mono" style={{ color: "rgba(255,255,255,0.18)" }}>DEMO · MOCK DATA</span>
        </div>

        <div className="p-6 space-y-4">
          {/* File name + verdict badge */}
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <p className="text-[10px] font-mono uppercase tracking-widest mb-1" style={{ color: "rgba(255,255,255,0.25)" }}>Evidence File</p>
              <p className="text-sm font-mono" style={{ color: "rgba(255,255,255,0.75)" }}>{report.file}</p>
            </div>
            <div
              className="flex items-center gap-2 px-4 py-2 rounded-xl shrink-0"
              style={{ background: vc.bg, border: `1px solid ${vc.border}` }}
            >
              <vc.Icon className="w-4 h-4" style={{ color: vc.color }} aria-hidden="true" />
              <span className="text-sm font-bold" style={{ color: vc.color }}>{report.verdictLabel}</span>
              <span className="text-sm font-mono font-bold" style={{ color: vc.color }}>{report.confidence}%</span>
            </div>
          </div>

          {/* Agent findings */}
          <div className="space-y-2">
            {report.agents.map((agent) => {
              const isNA = agent.verdict === "NOT_APPLICABLE";
              return (
                <div
                  key={agent.name}
                  className="rounded-xl px-4 py-3"
                  style={{
                    background: isNA ? "rgba(255,255,255,0.015)" : "rgba(255,255,255,0.04)",
                    border: `1px solid ${isNA ? "rgba(255,255,255,0.04)" : "rgba(255,255,255,0.07)"}`,
                    opacity: isNA ? 0.45 : 1,
                  }}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[11px] font-bold uppercase tracking-wide" style={{ color: "rgba(255,255,255,0.75)" }}>{agent.name}</span>
                    {!isNA ? (
                      <span className="text-[10px] font-mono font-bold" style={{
                        color: agent.verdict === "AUTHENTIC" ? "#34d399" : "#f43f5e",
                      }}>
                        {agent.verdict === "AUTHENTIC" ? "NO ANOMALIES" : "ANOMALIES FOUND"} · {agent.conf}%
                      </span>
                    ) : (
                      <span className="text-[10px] font-mono" style={{ color: "rgba(255,255,255,0.2)" }}>N/A</span>
                    )}
                  </div>
                  <p className="text-xs leading-relaxed" style={{ color: "rgba(255,255,255,0.45)" }}>{agent.finding}</p>
                </div>
              );
            })}
          </div>

          {/* Arbiter note */}
          <div
            className="rounded-xl px-4 py-4"
            style={{ background: "rgba(226,185,74,0.04)", border: "1px solid rgba(226,185,74,0.12)" }}
          >
            <p className="text-[10px] font-mono font-bold uppercase tracking-widest mb-2 flex items-center gap-2" style={{ color: "rgba(226,185,74,0.6)" }}>
              <Scale className="w-3.5 h-3.5" aria-hidden="true" /> Council Arbiter
            </p>
            <p className="text-sm leading-relaxed" style={{ color: "rgba(255,255,255,0.65)" }}>{report.arbiterNote}</p>
          </div>
        </div>
      </motion.div>
    </div>
  );
}

// ── 3D Glass Card ───────────────────────────────────────────────────────────
function Card3D({
  children,
  className,
  delay = 0,
  style,
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
  style?: React.CSSProperties;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const springConfig = { damping: 20, stiffness: 150 };
  const mouseX = useSpring(useMotionValue(50), springConfig);
  const mouseY = useSpring(useMotionValue(50), springConfig);
  const rotateX = useSpring(useMotionValue(0), springConfig);
  const rotateY = useSpring(useMotionValue(0), springConfig);

  const handleMouseMove = (e: React.MouseEvent) => {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * 100;
    const y = ((e.clientY - rect.top) / rect.height) * 100;
    const rX = ((e.clientY - rect.top) / rect.height - 0.5) * -10;
    const rY = ((e.clientX - rect.left) / rect.width - 0.5) * 10;
    mouseX.set(x);
    mouseY.set(y);
    rotateX.set(rX);
    rotateY.set(rY);
  };

  const handleMouseLeave = () => {
    mouseX.set(50);
    mouseY.set(50);
    rotateX.set(0);
    rotateY.set(0);
  };

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ delay, duration: 0.5 }}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      className={`glass-card-3d rounded-2xl p-8 flex flex-col items-center text-center cursor-default ${className ?? ""}`}
      style={{
        ...style,
        rotateX,
        rotateY,
        transformStyle: "preserve-3d",
      }}
    >
      <motion.div 
        className="absolute inset-0 rounded-2xl pointer-events-none z-0"
        style={{
          background: useTransform(
            [mouseX, mouseY],
            ([x, y]) => `radial-gradient(800px circle at ${x}% ${y}%, rgba(34, 211, 238, 0.08), transparent 40%)`
          ),
        }}
      />
      <div className="relative z-10 flex flex-col items-center">
        {children}
      </div>
    </motion.div>
  );
}

// ── Microscope Background ───────────────────────────────────────────────────
function MicroscopeBackground({ scrollY }: { scrollY: import("framer-motion").MotionValue<number> }) {
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      mouseX.set(e.clientX);
      mouseY.set(e.clientY);
    };
    window.addEventListener("mousemove", handleMouseMove);
    return () => window.removeEventListener("mousemove", handleMouseMove);
  }, [mouseX, mouseY]);

  const crosshairX = useSpring(useTransform(mouseX, [0, 2000], [0, 20]), { damping: 50, stiffness: 200 });
  const crosshairY = useSpring(useTransform(mouseY, [0, 1200], [0, 20]), { damping: 50, stiffness: 200 });

  return (
    <div className="fixed inset-0 pointer-events-none" aria-hidden="true">
      {/* Base ambient gradients */}
      <motion.div
        className="absolute"
        style={{
          top: "-10%", left: "8%",
          width: 700, height: 700,
          background: "radial-gradient(circle, rgba(79,70,229,0.18) 0%, transparent 70%)",
          filter: "blur(100px)",
          y: useTransform(scrollY, [0, 2000], [0, -200]),
        }}
      />
      <motion.div
        className="absolute"
        style={{
          top: "30%", right: "5%",
          width: 560, height: 560,
          background: "radial-gradient(circle, rgba(13,148,136,0.14) 0%, transparent 70%)",
          filter: "blur(80px)",
          y: useTransform(scrollY, [0, 2000], [0, -120]),
        }}
      />
      <motion.div
        className="absolute"
        style={{
          bottom: "10%", left: "30%",
          width: 480, height: 480,
          background: "radial-gradient(circle, rgba(34,211,238,0.08) 0%, transparent 70%)",
          filter: "blur(90px)",
          y: useTransform(scrollY, [0, 2000], [0, -80]),
        }}
      />

      {/* Evidence scanning grid */}
      <div className="microscope-evidence-grid" />

      {/* Horizontal scan lines */}
      <div className="microscope-scanline" style={{ top: "15%", "--scan-duration": "7s", "--scan-delay": "0s" } as React.CSSProperties} />
      <div className="microscope-scanline" style={{ top: "45%", "--scan-duration": "10s", "--scan-delay": "3s" } as React.CSSProperties} />
      <div className="microscope-scanline" style={{ top: "75%", "--scan-duration": "12s", "--scan-delay": "6s" } as React.CSSProperties} />

      {/* Crosshair markers — now reactive to mouse */}
      <motion.div 
        className="microscope-crosshair" 
        style={{ top: "20%", left: "15%", "--crosshair-size": "100px", "--pulse-duration": "5s", "--pulse-delay": "0s", x: crosshairX, y: crosshairY } as any} 
      />
      <motion.div 
        className="microscope-crosshair" 
        style={{ top: "60%", right: "20%", "--crosshair-size": "80px", "--pulse-duration": "6s", "--pulse-delay": "2s", x: useTransform(crosshairX, (v) => -v), y: useTransform(crosshairY, (v) => -v) } as any} 
      />
      <motion.div 
        className="microscope-crosshair" 
        style={{ bottom: "25%", left: "50%", "--crosshair-size": "140px", "--pulse-duration": "7s", "--pulse-delay": "4s", x: useTransform(crosshairX, (v) => v * 0.5), y: useTransform(crosshairY, (v) => v * 0.5) } as any} 
      />

      {/* Subtle dot grid overlay */}
      <div
        className="absolute inset-0"
        style={{
          backgroundImage: "radial-gradient(rgba(34,211,238,0.04) 1px, transparent 1px)",
          backgroundSize: "32px 32px",
        }}
      />
    </div>
  );
}

// ── Section Divider ─────────────────────────────────────────────────────────
const sectionBorder = { borderTop: "1px solid rgba(255,255,255,0.04)" } as const;

// ── Landing Page ──────────────────────────────────────────────────────────────
export default function LandingPage() {
  const router = useRouter();
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [showSuccessModal, setShowSuccessModal] = useState(false);

  const { scrollY } = useScroll();
  const scrollMotion = useMotionValue(0);

  useEffect(() => {
    return scrollY.on("change", (v) => scrollMotion.set(v));
  }, [scrollY, scrollMotion]);

  const handleFileSelected = useCallback((f: File) => {
    setUploadedFile(f);
    setShowUploadModal(false);
    setShowSuccessModal(true);
  }, []);

  const handleNewUpload = useCallback(() => {
    setUploadedFile(null);
    setShowSuccessModal(false);
    setShowUploadModal(true);
  }, []);

  const handleStartAnalysis = useCallback(() => {
    if (!uploadedFile) return;
    (window as { __forensic_pending_file?: File }).__forensic_pending_file = uploadedFile;
    sessionStorage.setItem("forensic_auto_start", "true");
    router.push("/evidence");
  }, [uploadedFile, router]);

  useEffect(() => {
    autoLoginAsInvestigator().catch(() => {});
  }, []);

  return (
    <div
      className="min-h-screen relative overflow-x-hidden"
      style={{ backgroundColor: "#080C14" }}
    >
      {/* ── Microscope scanning background ── */}
      <MicroscopeBackground scrollY={scrollMotion} />

      {/* ── Navbar ── */}
      <nav
        aria-label="Main navigation"
        className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-4"
        style={{
          background: "rgba(8,12,20,0.95)",
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
          borderBottom: "1px solid rgba(255,255,255,0.05)",
        }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-9 h-9 rounded-lg flex items-center justify-center text-sm font-bold"
            style={{
              background: "linear-gradient(135deg, #0891b2 0%, #22d3ee 100%)",
              color: "#fff",
            }}
          >
            FC
          </div>
          <span className="font-semibold text-white tracking-tight text-base">Forensic Council</span>
        </div>

      </nav>

      {/* ── Hero ── */}
      <section className="relative min-h-screen flex flex-col items-center justify-center pt-32 pb-20 px-6 text-center">
        {/* Floating 3D gradient orb behind hero */}
        <motion.div
          className="absolute pointer-events-none"
          style={{
            width: 500, height: 500,
            background: "conic-gradient(from 0deg, rgba(79,70,229,0.12), rgba(34,211,238,0.08), rgba(167,139,250,0.1), rgba(79,70,229,0.12))",
            borderRadius: "50%",
            filter: "blur(80px)",
            y: useTransform(scrollY, [0, 800], [0, -150]),
            scale: useTransform(scrollY, [0, 800], [1, 0.8]),
          }}
        />

        {/* Title */}
        <motion.h1
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15, duration: 0.6 }}
          className="text-4xl md:text-6xl lg:text-[4.5rem] font-bold tracking-tight mb-2 leading-[0.95] relative z-10 max-w-4xl mx-auto"
          style={{
            background: "linear-gradient(160deg, #ffffff 0%, #cbd5e1 100%)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            backgroundSize: "200% 200%",
            animation: "text-scan-reveal 4s ease infinite",
            filter: "drop-shadow(0 0 30px rgba(255, 255, 255, 0.1))",
            y: useTransform(scrollY, [0, 600], [0, -60]),
          }}
        >
          Multi Agent Forensic
        </motion.h1>
        
        <motion.h1
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25, duration: 0.6 }}
          className="text-4xl md:text-6xl lg:text-[4.5rem] font-bold tracking-tight mb-8 leading-[0.95] relative z-10 max-w-4xl mx-auto"
          style={{
            background: "linear-gradient(160deg, #22d3ee 0%, #ffffff 50%, #22d3ee 100%)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            backgroundClip: "text",
            backgroundSize: "200% 200%",
            animation: "gradient-shift 6s ease infinite, text-scan-reveal 5s ease-in-out infinite",
            filter: "drop-shadow(0 0 40px rgba(34, 211, 238, 0.4))",
            y: useTransform(scrollY, [0, 600], [0, -40]),
          }}
        >
          Evidence Analysis System
        </motion.h1>

        {/* Sub-headline / Subtitle */}
        <motion.p
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4, duration: 0.5 }}
          className="text-base md:text-lg font-medium mb-10 max-w-2xl leading-relaxed relative z-20"
          style={{
            color: "rgba(248,250,252,0.85)",
            y: useTransform(scrollY, [0, 600], [0, -20]),
            filter: "drop-shadow(0 0 20px rgba(0,0,0,0.5))",
          }}
        >
          This app uses five specialist agents to analyse and verify digital forensic evidence and an arbiter oversees these individual agent findings to create a cohesive and comprehensive evidence analysis report.
        </motion.p>

        {/* CTA Button */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.55, duration: 0.4 }}
          className="relative z-10"
          style={{ y: useTransform(scrollY, [0, 600], [0, -10]) }}
        >
          <motion.button
            onClick={() => setShowUploadModal(true)}
            whileHover={{ 
              scale: 1.04, 
              background: "rgba(34, 211, 238, 0.04)", 
              borderColor: "rgba(34, 211, 238, 0.4)",
              color: "#22d3ee",
              boxShadow: "0 0 40px rgba(34, 211, 238, 0.25)"
            }}
            whileTap={{ scale: 0.97 }}
            className="inline-flex items-center gap-3 px-8 py-4 rounded-2xl text-base font-semibold cursor-pointer transition-all duration-200"
            style={{
              background: "linear-gradient(135deg, #0891b2 0%, #22d3ee 100%)",
              color: "#fff",
              border: "1px solid transparent",
              boxShadow: "0 4px 30px rgba(34, 211, 238, 0.3)",
            }}
          >
            Begin Analysis
            <ArrowRight className="w-5 h-5" aria-hidden="true" />
          </motion.button>
        </motion.div>
      </section>

      {/* ── How It Works ── */}
      <section className="relative py-28 px-6 z-10 section-gradient-3d">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <p className="text-xs tracking-[0.25em] mb-3 font-mono" style={{ color: "rgba(167,139,250,0.5)" }}>
              THE PROCESS
            </p>
            <h2 id="how-it-works-heading" className="text-3xl md:text-5xl font-bold text-white">
              How Forensic Council Works
            </h2>
            <p className="text-base mt-4 max-w-xl mx-auto leading-relaxed" style={{ color: "rgba(255,255,255,0.38)" }}>
              From upload to signed verdict in four automated steps.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {HOW_IT_WORKS.map((step, i) => (
              <Card3D key={step.step} delay={i * 0.1}>
                {/* Step Number Badge */}
                <div className="absolute top-4 left-4 font-mono text-[10px] tracking-widest text-white/20 border border-white/5 px-2 py-0.5 rounded-full">
                  STEP {step.step}
                </div>

                {/* Animated Graphic */}
                <motion.div
                  animate={{ scale: [1, 1.05, 1], rotate: [0, 2, 0] }}
                  transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
                  className="w-14 h-14 rounded-2xl flex items-center justify-center mb-6 relative z-10"
                  style={{
                    background: `rgba(${step.rgb},0.08)`,
                    border: `1px solid rgba(${step.rgb},0.2)`,
                    boxShadow: `0 0 20px rgba(${step.rgb},0.1)`,
                  }}
                >
                  <step.icon className="w-7 h-7" style={{ color: step.color }} aria-hidden="true" />
                </motion.div>

                {/* Step Name */}
                <h3 className="text-xl font-bold text-white tracking-tight mb-4 relative z-10">{step.title}</h3>

                {/* Step Description */}
                <p className="text-sm leading-relaxed mb-6 flex-grow relative z-10" style={{ color: "rgba(255,255,255,0.5)" }}>
                  {step.desc}
                </p>

                <div
                  className="mt-2 inline-flex items-center px-3 py-1.5 rounded-lg relative z-10"
                  style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.05)" }}
                >
                  <span className="text-[9px] font-mono uppercase tracking-widest" style={{ color: "rgba(255,255,255,0.2)" }}>
                    {step.tag}
                  </span>
                </div>
              </Card3D>
            ))}
          </div>
        </div>
      </section>

      {/* ── Meet the Agents ── */}
      <section className="relative py-28 px-6 z-10 section-gradient-3d" aria-labelledby="agents-heading" style={sectionBorder}>
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <p className="text-xs tracking-[0.25em] mb-3 font-mono" style={{ color: "rgba(34,211,238,0.6)" }}>
              THE COUNCIL
            </p>
            <h2 id="agents-heading" className="text-3xl md:text-5xl font-bold text-white">
              Meet the Agents
            </h2>
            <p className="text-base mt-4 max-w-xl mx-auto leading-relaxed" style={{ color: "rgba(255,255,255,0.38)" }}>
              Six specialists with distinct forensic expertise, deliberating as one council.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {AGENTS.map((agent, i) => (
              <Card3D key={agent.id} delay={i * 0.07}>
                {/* Animated Graphic */}
                <motion.div
                  animate={{ scale: [1, 1.08, 1] }}
                  transition={{ duration: 5, repeat: Infinity, ease: "easeInOut", delay: i * 0.2 }}
                  className="w-14 h-14 rounded-2xl flex items-center justify-center mb-6 relative z-10"
                  style={{
                    background: `rgba(${agent.bgRgb},0.08)`,
                    border: `1px solid rgba(${agent.bgRgb},0.2)`,
                    boxShadow: `0 0 25px rgba(${agent.bgRgb},0.12)`,
                  }}
                >
                  <agent.icon className="w-7 h-7" style={{ color: agent.color }} aria-hidden="true" />
                </motion.div>

                {/* Agent Name */}
                <h3 className="text-xl font-bold text-white mb-4 tracking-tight relative z-10">{agent.name}</h3>

                {/* Description */}
                <p className="text-sm leading-relaxed flex-grow relative z-10" style={{ color: "rgba(255,255,255,0.45)" }}>
                  {agent.desc}
                </p>
              </Card3D>
            ))}
          </div>
        </div>
      </section>

      {/* ── Example Report ── */}
      <section className="relative py-24 px-6 z-10">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <p className="text-xs tracking-[0.25em] mb-3 font-mono" style={{ color: "rgba(34,211,238,0.6)" }}>
              SAMPLE OUTPUT
            </p>
            <h2 className="text-3xl md:text-5xl font-bold text-white">
              Example Report
            </h2>
            <p className="text-base mt-4 max-w-xl mx-auto leading-relaxed" style={{ color: "rgba(255,255,255,0.38)" }}>
              A preview of what the Council produces for each evidence type.
            </p>
          </div>
          <ExampleReportSection />
        </div>
      </section>

      {/* ── Modals ── */}
      <AnimatePresence>
        {showUploadModal && (
          <UploadModal key="upload" onClose={() => setShowUploadModal(false)} onFileSelected={handleFileSelected} />
        )}
        {showSuccessModal && uploadedFile && (
          <UploadSuccessModal key="success" file={uploadedFile} onNewUpload={handleNewUpload} onStartAnalysis={handleStartAnalysis} />
        )}
      </AnimatePresence>

      <GlobalFooter />
    </div>
  );
}
