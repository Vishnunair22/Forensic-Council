"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowRight, UploadCloud, X, RefreshCw,
  FileImage, FileAudio, FileVideo, FileText,
  Image as ImageIcon, Mic, Crosshair, Video, FileCode2, Scale,
  ShieldCheck, Cpu, FileSignature, CheckCircle, AlertTriangle,
} from "lucide-react";
import { autoLoginAsInvestigator } from "@/lib/api";
import { __pendingFileStore } from "@/lib/pendingFileStore";

// ── Agent data ────────────────────────────────────────────────────────────────
const AGENTS = [
  { id: "AGT-01", name: "Image Forensics", icon: ImageIcon, color: "#22d3ee", bgRgb: "34,211,238", badge: "Visual Authenticity", desc: "ELA analysis, copy-move detection, PRNU camera noise fingerprints to expose visual splicing and region tampering." },
  { id: "AGT-02", name: "Audio Forensics", icon: Mic, color: "#a78bfa", bgRgb: "167,139,250", badge: "Acoustic Integrity", desc: "Wav2Vec2 deepfake detection and spectral analysis to catch voice cloning, audio splicing, and synthesis artefacts." },
  { id: "AGT-03", name: "Object Detection", icon: Crosshair, color: "#f59e0b", bgRgb: "245,158,11", badge: "Contextual Analysis", desc: "YOLOv8 lighting, shadow, and reflection anomaly detection to spot compositing errors and contextual inconsistencies." },
  { id: "AGT-04", name: "Video Forensics", icon: Video, color: "#f43f5e", bgRgb: "244,63,94", badge: "Temporal Analysis", desc: "Frame-by-frame face-swap detection and temporal inconsistency scans across the full video timeline." },
  { id: "AGT-05", name: "Metadata Expert", icon: FileCode2, color: "#34d399", bgRgb: "52,211,153", badge: "Digital Footprint", desc: "EXIF/XMP extraction, GPS cross-reference, solar positioning checks, and device fingerprinting." },
  { id: "AGT-06", name: "Council Arbiter", icon: Scale, color: "#e2b94a", bgRgb: "226,185,74", badge: "Final Synthesis", desc: "Cross-references all agent findings, resolves conflicts, and synthesises a unified ECDSA P-256 signed verdict." },
] as const;

const HOW_IT_WORKS = [
  { step: "01", icon: UploadCloud, title: "Secure Ingestion", desc: "File uploaded over TLS. SHA-256 hash calculated immediately to establish an immutable chain of custody.", tag: "Chain of Custody", color: "#22d3ee", rgb: "34,211,238" },
  { step: "02", icon: Cpu, title: "Multi-Agent Scan", desc: "Five specialist agents run parallel deep analysis on image, audio, video, and metadata evidence.", tag: "5 Agents Active", color: "#a78bfa", rgb: "167,139,250" },
  { step: "03", icon: Scale, title: "Council Deliberation", desc: "The Arbiter cross-references all agent findings, resolves conflicts, and synthesises a unified confidence score.", tag: "Arbiter Review", color: "#f59e0b", rgb: "245,158,11" },
  { step: "04", icon: FileSignature, title: "Cryptographic Verdict", desc: "Tamper-evident ECDSA P-256 signed forensic report — court-admissible and permanently immutable.", tag: "Verdict Signed", color: "#34d399", rgb: "52,211,153" },
] as const;

// ── Mock report data ──────────────────────────────────────────────────────────
const REPORT_TABS = ["Image", "Text", "Audio", "Video"] as const;
type ReportTab = (typeof REPORT_TABS)[number];
const TAB_ICONS: Record<ReportTab, typeof FileImage> = { Image: FileImage, Text: FileText, Audio: FileAudio, Video: FileVideo };

const MOCK_REPORTS: Record<ReportTab, {
  file: string; verdict: string; verdictLabel: string; confidence: number;
  agents: { name: string; verdict: string; conf: number; finding: string }[];
  arbiterNote: string;
}> = {
  "Image": {
    file: "evidence_photo_2024.jpg", verdict: "MANIPULATED", verdictLabel: "Manipulation Detected", confidence: 91,
    agents: [
      { name: "Image Forensics", verdict: "SUSPICIOUS", conf: 94, finding: "ELA heatmap reveals region-inconsistent JPEG compression in top-right sky quadrant." },
      { name: "Object & Weapon Analyst", verdict: "SUSPICIOUS", conf: 87, finding: "Shadow direction inconsistency at 14\u00b0 offset from main subject." },
      { name: "Metadata Expert", verdict: "SUSPICIOUS", conf: 78, finding: "Camera model inconsistent with embedded ICC color profile." },
      { name: "Audio Forensics", verdict: "NOT_APPLICABLE", conf: 0, finding: "File type not applicable for audio analysis." },
      { name: "Video Forensics", verdict: "NOT_APPLICABLE", conf: 0, finding: "File type not applicable for video analysis." },
    ],
    arbiterNote: "Three independent agents corroborate manipulative artefacts.",
  },
  "Text": {
    file: "document_verification.pdf", verdict: "AUTHENTIC", verdictLabel: "Authentic", confidence: 95,
    agents: [
      { name: "Text Analysis", verdict: "AUTHENTIC", conf: 98, finding: "No anomalies detected in document structure." },
      { name: "Metadata Expert", verdict: "AUTHENTIC", conf: 92, finding: "Document timestamps consistent with claimed origin." },
      { name: "Image Forensics", verdict: "NOT_APPLICABLE", conf: 0, finding: "File type not applicable for image analysis." },
      { name: "Audio Forensics", verdict: "NOT_APPLICABLE", conf: 0, finding: "File type not applicable for audio analysis." },
      { name: "Video Forensics", verdict: "NOT_APPLICABLE", conf: 0, finding: "File type not applicable for video analysis." },
    ],
    arbiterNote: "Text analysis confirms authenticity across all applicable metrics.",
  },
  "Audio": {
    file: "voice_recording.wav", verdict: "LIKELY_MANIPULATED", verdictLabel: "Likely Manipulated", confidence: 78,
    agents: [
      { name: "Audio Forensics", verdict: "SUSPICIOUS", conf: 82, finding: "Wav2Vec2 deepfake classifier: 82% confidence." },
      { name: "Metadata Expert", verdict: "SUSPICIOUS", conf: 71, finding: "Editing software metadata inconsistent with claimed field recording." },
      { name: "Image Forensics", verdict: "NOT_APPLICABLE", conf: 0, finding: "File type not applicable for image analysis." },
      { name: "Object & Weapon Analyst", verdict: "NOT_APPLICABLE", conf: 0, finding: "File type not applicable for object analysis." },
      { name: "Video Forensics", verdict: "NOT_APPLICABLE", conf: 0, finding: "File type not applicable for video analysis." },
    ],
    arbiterNote: "Audio synthesis artefacts are consistent across acoustic and metadata analysis.",
  },
  "Video": {
    file: "security_footage.mp4", verdict: "AUTHENTIC", verdictLabel: "Authentic", confidence: 88,
    agents: [
      { name: "Video Forensics", verdict: "AUTHENTIC", conf: 90, finding: "No face-swap artefacts across 3,241 frames." },
      { name: "Image Forensics", verdict: "AUTHENTIC", conf: 86, finding: "Per-keyframe ELA analysis shows uniform JPEG compression." },
      { name: "Object & Weapon Analyst", verdict: "AUTHENTIC", conf: 84, finding: "Lighting direction and shadow consistency validated." },
      { name: "Metadata Expert", verdict: "AUTHENTIC", conf: 91, finding: "Device fingerprint matches claimed camera model." },
      { name: "Audio Forensics", verdict: "AUTHENTIC", conf: 83, finding: "No synthetic speech artefacts in embedded audio track." },
    ],
    arbiterNote: "All five agents converge on authentic. No evidence of manipulation found.",
  },
};

// ── Framer Motion Variants ────────────────────────────────────────────────────
const scaleIn = {
  hidden: { opacity: 0, scale: 0.85 },
  visible: { opacity: 1, scale: 1, transition: { duration: 0.3, ease: [0.34, 1.56, 0.64, 1] as const } },
  exit: { opacity: 0, scale: 0.85, transition: { duration: 0.2 } },
};

const overlayVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.25 } },
  exit: { opacity: 0, transition: { duration: 0.2 } },
};

const cardHover = {
  rest: { scale: 1, boxShadow: "0 0 0px rgba(34,211,238,0)" },
  hover: {
    scale: 1.02,
    boxShadow: "0 0 20px rgba(34,211,238,0.1)",
    borderColor: "rgba(34, 211, 238, 0.25)",
    transition: { duration: 0.3, ease: "easeOut" as const },
  },
};

// ── Upload Modal ──────────────────────────────────────────────────────────────
function UploadModal({ onClose, onFileSelected }: { onClose: () => void; onFileSelected: (f: File) => void }) {
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const handleFile = useCallback((f: File) => { onFileSelected(f); }, [onFileSelected]);

  return (
    <motion.div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.6)", backdropFilter: "blur(12px)" }}
      variants={overlayVariants}
      initial="hidden"
      animate="visible"
      exit="exit"
      onClick={onClose}
    >
      <motion.div
        className="relative w-full max-w-lg"
        variants={scaleIn}
        initial="hidden"
        animate="visible"
        exit="exit"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="rounded-3xl overflow-hidden border border-white/[0.07] bg-white/[0.03]"
          style={{ backdropFilter: "blur(24px) saturate(160%)", boxShadow: "0 32px 80px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.08)" }}>

          {/* Header accent bar */}
          <div className="relative w-full h-20 origin-top"
            style={{ background: "linear-gradient(135deg, rgba(34,211,238,0.15) 0%, rgba(79,70,229,0.12) 100%)", clipPath: "polygon(0 0, 50% 100%, 100% 0)", transform: "rotateX(180deg)" }}
          />

          <div className="relative p-10 pt-6 -mt-2">
            <div className="absolute -top-24 -right-24 w-48 h-48 bg-cyan-500/10 blur-[80px] pointer-events-none" />
            <button onClick={onClose} className="absolute top-6 right-6 p-2 rounded-xl cursor-pointer hover:bg-white/5 transition-colors border border-white/5" aria-label="Close upload modal">
              <X className="w-5 h-5 text-white/40" />
            </button>

            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15, duration: 0.35 }}>
              <div className="mb-8">
                <h3 className="text-2xl font-bold text-white tracking-tight">Upload Evidence</h3>
              </div>

              <motion.div
                className="group relative rounded-2xl border-2 border-dashed p-12 text-center cursor-pointer overflow-hidden"
                style={{ borderColor: isDragging ? "rgba(34,211,238,0.5)" : "rgba(255,255,255,0.08)", background: isDragging ? "rgba(34,211,238,0.05)" : "rgba(255,255,255,0.02)" }}
                whileHover={{ borderColor: "rgba(34,211,238,0.3)", background: "rgba(34,211,238,0.03)" }}
                transition={{ duration: 0.2 }}
                onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={(e) => { e.preventDefault(); setIsDragging(false); const f = e.dataTransfer.files[0]; if (f) handleFile(f); }}
                onClick={() => fileInputRef.current?.click()}
              >
                <div className="absolute inset-0 bg-gradient-to-b from-cyan-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
                <div className="relative z-10">
                  <motion.div
                    className="w-16 h-16 rounded-2xl bg-cyan-500/10 flex items-center justify-center mx-auto mb-5 border border-cyan-500/20"
                    whileHover={{ scale: 1.1 }}
                    transition={{ type: "spring", stiffness: 400, damping: 17 }}
                  >
                    <UploadCloud className="w-8 h-8 text-cyan-400" />
                  </motion.div>
                  <p className="text-lg font-semibold text-white mb-2">Drop file here or <span className="text-cyan-400 underline underline-offset-4 decoration-cyan-400/30">browse</span></p>
                  <div className="flex items-center justify-center gap-3 opacity-40">
                    <FileImage className="w-4 h-4" /><FileVideo className="w-4 h-4" /><FileAudio className="w-4 h-4" /><FileText className="w-4 h-4" />
                  </div>
                </div>
                <input ref={fileInputRef} type="file" className="hidden" accept="image/*,audio/*,video/*" onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }} />
              </motion.div>

              <div className="mt-8 flex flex-col gap-2">
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-500" />
                  <p className="text-sm font-medium text-white/60">Supported: Image, Video, Audio, Document</p>
                </div>
                <p className="text-xs text-white/30 ml-3.5">Maximum file size: 50 MB &middot; SHA-256 integrity check performed automatically.</p>
              </div>
            </motion.div>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}

// ── Upload Success Modal ──────────────────────────────────────────────────────
function UploadSuccessModal({ file, onNewUpload, onStartAnalysis }: { file: File; onNewUpload: () => void; onStartAnalysis: () => void }) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    if (!file) { setPreviewUrl(null); return; }
    const isMedia = file.type.startsWith("image/") || file.type.startsWith("video/") || /\.(jpe?g|png|gif|bmp|webp|jfif|mp4|webm|mov|ogg)$/i.test(file.name);
    if (isMedia) {
      const reader = new FileReader();
      reader.onloadend = () => setPreviewUrl(reader.result as string);
      reader.onerror = () => setHasError(true);
      reader.readAsDataURL(file);
    } else { setPreviewUrl(null); }
  }, [file]);

  const isVideo = file.type.startsWith("video/") || /\.(mp4|webm|mov|ogg)$/i.test(file.name);
  const FileTypeIcon = file.type.startsWith("image/") ? FileImage : file.type.startsWith("audio/") ? FileAudio : isVideo ? FileVideo : FileText;

  return (
    <motion.div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.4)", backdropFilter: "blur(12px)" }}
      variants={overlayVariants}
      initial="hidden"
      animate="visible"
      exit="exit"
    >
      <motion.div
        className="relative w-full max-w-sm text-center overflow-hidden rounded-[2rem] p-10 border border-white/[0.06]"
        style={{ background: "transparent" }}
        variants={scaleIn}
        initial="hidden"
        animate="visible"
        exit="exit"
      >
        <div className="absolute -top-40 -left-40 w-80 h-80 rounded-full pointer-events-none" style={{ background: "radial-gradient(circle, rgba(34,211,238,0.08) 0%, transparent 70%)" }} />
        <div className="absolute -bottom-32 -right-32 w-64 h-64 rounded-full pointer-events-none" style={{ background: "radial-gradient(circle, rgba(52,211,153,0.06) 0%, transparent 70%)" }} />

        <motion.div
          className="w-28 h-28 rounded-full mx-auto mb-8 overflow-hidden flex items-center justify-center relative z-10 border border-white/[0.08] bg-white/[0.03]"
          style={{ boxShadow: "0 8px 40px rgba(0,0,0,0.3), inset 0 0 30px rgba(34,211,238,0.03)" }}
          animate={{ scale: [1, 1.03, 1] }}
          transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
        >
          {previewUrl && !hasError ? (
            isVideo ? (
              <video key={previewUrl} src={previewUrl} className="w-full h-full object-cover" muted loop autoPlay playsInline onError={() => setHasError(true)} />
            ) : (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img key={previewUrl} src={previewUrl} alt="File preview" className="w-full h-full object-cover" onError={() => setHasError(true)} />
            )
          ) : (
            <div className="flex flex-col items-center gap-2">
              <FileTypeIcon className="w-10 h-10 text-cyan-400/50" aria-hidden="true" />
              <span className="text-[9px] font-mono text-cyan-400/30 uppercase tracking-widest">NO PREVIEW</span>
            </div>
          )}
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25, duration: 0.4 }}>
          <div className="flex flex-col items-center mb-10">
            <div className="inline-flex items-center gap-2 mb-4 px-4 py-1.5 rounded-full bg-emerald-500/[0.08] border border-emerald-500/[0.15]">
              <motion.div
                className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]"
                animate={{ opacity: [1, 0.4, 1] }}
                transition={{ duration: 1.5, repeat: Infinity }}
              />
              <span className="text-[11px] font-bold text-emerald-400 tracking-wider uppercase">Evidence Ready</span>
            </div>
            <h3 className="text-white text-lg font-bold truncate max-w-full px-2 mb-2 leading-tight">{file.name}</h3>
            <div className="flex items-center gap-3 text-[11px] font-mono text-white/30 uppercase tracking-widest">
              <span>{file.type.split('/')[1] || "BINARY"}</span>
              <span className="w-1 h-1 rounded-full bg-white/15" />
              <span>{(file.size / (1024 * 1024)).toFixed(2)} MB</span>
            </div>
          </div>

          <div className="flex gap-3">
            <motion.button
              onClick={onNewUpload}
              className="flex-1 py-3.5 rounded-full text-xs font-semibold cursor-pointer flex items-center justify-center gap-2 text-white/50 hover:text-white/80 transition-all duration-300"
              style={{ background: "transparent", border: "1px solid rgba(255,255,255,0.1)" }}
              whileHover={{ scale: 1.02, background: "rgba(255,255,255,0.05)", borderColor: "rgba(255,255,255,0.2)" }}
              whileTap={{ scale: 0.98 }}
            >
              <RefreshCw className="w-3.5 h-3.5" /> Reset
            </motion.button>
            <motion.button
              onClick={onStartAnalysis}
              className="flex-[1.5] py-3.5 rounded-full text-sm font-bold cursor-pointer flex items-center justify-center gap-2 text-white transition-all duration-300"
              style={{ background: "linear-gradient(135deg, rgba(6,182,212,0.9) 0%, rgba(34,211,238,0.9) 100%)", border: "1px solid rgba(34,211,238,0.3)", boxShadow: "0 4px 24px rgba(34,211,238,0.25)" }}
              whileHover={{ scale: 1.03, background: "transparent", borderColor: "rgba(34,211,238,0.5)", boxShadow: "0 6px 32px rgba(34,211,238,0.15)" }}
              whileTap={{ scale: 0.97 }}
            >
              Analyse <ArrowRight className="w-4 h-4" />
            </motion.button>
          </div>
        </motion.div>
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
      <div className="flex gap-2 mb-6 flex-wrap" role="tablist" aria-label="Example report types">
        {REPORT_TABS.map((tab, i) => {
          const TabIcon = TAB_ICONS[tab];
          return (
            <motion.button
              key={tab}
              role="tab"
              id={`tab-${tab}`}
              aria-selected={activeTab === i}
              aria-controls={`panel-${tab}`}
              onClick={() => setActiveTab(i)}
              className="px-5 py-2 rounded-xl text-sm font-medium cursor-pointer flex items-center gap-2 border"
              style={activeTab === i
                ? { background: "rgba(34,211,238,0.1)", borderColor: "rgba(34,211,238,0.25)", color: "#22d3ee" }
                : { background: "rgba(255,255,255,0.03)", borderColor: "rgba(255,255,255,0.06)", color: "rgba(255,255,255,0.4)" }}
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
            >
              <TabIcon className="w-4 h-4" aria-hidden="true" /> {tab}
            </motion.button>
          );
        })}
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={activeTab}
          role="tabpanel"
          id={`panel-${tabKey}`}
          aria-labelledby={`tab-${tabKey}`}
          className="rounded-2xl overflow-hidden border border-white/[0.07] bg-white/[0.03]"
          style={{ backdropFilter: "blur(24px)", boxShadow: "inset 0 1px 0 rgba(255,255,255,0.06)" }}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.25 }}
        >
          <div className="px-6 py-4 border-b flex items-center justify-between border-white/[0.05]">
            <div className="flex items-center gap-2.5">
              <ShieldCheck className="w-4 h-4 text-cyan-400/50" aria-hidden="true" />
              <span className="text-xs font-mono tracking-widest text-white/30">FORENSIC COUNCIL</span>
            </div>
            <span className="text-xs font-mono text-white/[0.18]">DEMO &middot; MOCK DATA</span>
          </div>
          <div className="p-6 space-y-4">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div>
                <p className="text-[10px] font-mono uppercase tracking-widest mb-1 text-white/25">Evidence File</p>
                <p className="text-sm font-mono text-white/75">{report.file}</p>
              </div>
              <div className="flex items-center gap-2 px-4 py-2 rounded-xl shrink-0" style={{ background: vc.bg, border: `1px solid ${vc.border}` }}>
                <vc.Icon className="w-4 h-4" style={{ color: vc.color }} aria-hidden="true" />
                <span className="text-sm font-bold" style={{ color: vc.color }}>{report.verdictLabel}</span>
                <span className="text-sm font-mono font-bold" style={{ color: vc.color }}>{report.confidence}%</span>
              </div>
            </div>
            <div className="space-y-2">
              {report.agents.map((agent) => {
                const isNA = agent.verdict === "NOT_APPLICABLE";
                return (
                  <div key={agent.name} className="rounded-xl px-4 py-3 border" style={{ background: isNA ? "rgba(255,255,255,0.015)" : "rgba(255,255,255,0.04)", borderColor: isNA ? "rgba(255,255,255,0.04)" : "rgba(255,255,255,0.07)", opacity: isNA ? 0.45 : 1 }}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[11px] font-bold uppercase tracking-wide text-white/75">{agent.name}</span>
                      {!isNA ? (
                        <span className="text-[10px] font-mono font-bold" style={{ color: agent.verdict === "AUTHENTIC" ? "#34d399" : "#f43f5e" }}>
                          {agent.verdict === "AUTHENTIC" ? "NO ANOMALIES" : "ANOMALIES FOUND"} &middot; {agent.conf}%
                        </span>
                      ) : (<span className="text-[10px] font-mono text-white/20">N/A</span>)}
                    </div>
                    <p className="text-xs leading-relaxed text-white/45">{agent.finding}</p>
                  </div>
                );
              })}
            </div>
            <div className="rounded-xl px-4 py-4 border" style={{ background: "rgba(226,185,74,0.04)", borderColor: "rgba(226,185,74,0.12)" }}>
              <p className="text-[10px] font-mono font-bold uppercase tracking-widest mb-2 flex items-center gap-2 text-amber-400/60">
                <Scale className="w-3.5 h-3.5" aria-hidden="true" /> Council Arbiter
              </p>
              <p className="text-sm leading-relaxed text-white/65">{report.arbiterNote}</p>
            </div>
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

// ── Landing Page ──────────────────────────────────────────────────────────────
export default function LandingPage() {
  const router = useRouter();
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [showSuccessModal, setShowSuccessModal] = useState(false);

  useEffect(() => {
    requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior }));
  }, []);

  useEffect(() => {
    const handleReset = () => {
      setShowUploadModal(false);
      setShowSuccessModal(false);
      setUploadedFile(null);
      sessionStorage.removeItem("fc_show_loading");
    };
    window.addEventListener("fc:reset-home", handleReset);
    return () => window.removeEventListener("fc:reset-home", handleReset);
  }, []);

  const handleFileSelected = useCallback((f: File) => { setUploadedFile(f); setShowUploadModal(false); setShowSuccessModal(true); }, []);
  const handleNewUpload = useCallback(() => { setUploadedFile(null); setShowSuccessModal(false); setShowUploadModal(true); }, []);

  const handleStartAnalysis = useCallback(() => {
    if (!uploadedFile) return;
    __pendingFileStore.file = uploadedFile;
    sessionStorage.setItem("forensic_auto_start", "true");
    sessionStorage.setItem("fc_show_loading", "true");
    router.push("/evidence");
  }, [uploadedFile, router]);

  useEffect(() => { autoLoginAsInvestigator().catch(() => {}); }, []);

  return (
    <div className="min-h-screen relative overflow-x-hidden">
      {/* ── Hero ── */}
      <section className="relative min-h-screen flex flex-col items-center justify-center pt-32 pb-20 px-6 text-center outline-none" id="hero">
        <motion.h1
          className="text-4xl md:text-6xl lg:text-[4.5rem] font-bold tracking-tight mb-2 leading-[0.95] relative z-10 max-w-4xl mx-auto text-white"
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.15 }}
        >
          Multi Agent Forensic
        </motion.h1>
        <motion.h1
          className="text-4xl md:text-6xl lg:text-[4.5rem] font-bold tracking-tight mb-8 leading-[0.95] relative z-10 max-w-4xl mx-auto text-cyan-400"
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0, backgroundPosition: ["0% 50%", "100% 50%", "0% 50%"] }}
          transition={{ duration: 0.6, delay: 0.25, backgroundPosition: { duration: 6, repeat: Infinity, ease: "easeInOut" } }}
        >
          Evidence Analysis System
        </motion.h1>
        <motion.p
          className="text-base md:text-lg font-medium mb-10 max-w-2xl leading-relaxed relative z-20 text-slate-100/85"
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.4 }}
        >
          This app uses five specialist agents to analyse and verify digital forensic evidence and an arbiter oversees these individual agent findings to create a cohesive and comprehensive evidence analysis report.
        </motion.p>
        <motion.div
          className="relative z-10"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.55 }}
        >
          <motion.button
            onClick={() => setShowUploadModal(true)}
            className="inline-flex items-center gap-3 px-8 py-4 rounded-2xl text-base font-semibold cursor-pointer text-white border border-transparent"
            style={{ background: "linear-gradient(135deg, #0891b2 0%, #22d3ee 100%)", boxShadow: "0 4px 30px rgba(34, 211, 238, 0.3)" }}
            whileHover={{ scale: 1.05, boxShadow: "0 6px 40px rgba(34, 211, 238, 0.4)", background: "transparent", border: "1px solid rgba(34, 211, 238, 0.5)" }}
            whileTap={{ scale: 0.95 }}
          >
            Begin Analysis <ArrowRight className="w-5 h-5" aria-hidden="true" />
          </motion.button>
        </motion.div>
      </section>

      {/* ── How It Works ── */}
      <section className="relative py-28 px-6 z-10 border-t border-white/[0.04]">
        <div className="absolute inset-0 pointer-events-none" style={{ background: "radial-gradient(ellipse 80% 60% at 50% 50%, rgba(79,70,229,0.06) 0%, rgba(34,211,238,0.03) 40%, transparent 70%)" }} />
        <div className="max-w-6xl mx-auto relative">
          <motion.div className="text-center mb-16" initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.5 }}>
            <p className="text-xs tracking-[0.25em] mb-3 font-mono text-violet-400/50">THE PROCESS</p>
            <h2 id="how-it-works-heading" className="text-3xl md:text-5xl font-bold text-white">How Forensic Council Works</h2>
            <p className="text-base mt-4 max-w-xl mx-auto leading-relaxed text-white/[0.38]">From upload to signed verdict in four automated steps.</p>
          </motion.div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {HOW_IT_WORKS.map((step, i) => (
              <motion.div
                key={step.step}
                className="rounded-2xl p-8 flex flex-col items-center text-center cursor-default relative border border-white/[0.08] bg-white/[0.03]"
                style={{ backdropFilter: "blur(20px) saturate(150%)", boxShadow: "inset 0 1px 0 rgba(255,255,255,0.08), 0 8px 32px rgba(0,0,0,0.3)" }}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: i * 0.1 }}
                variants={cardHover}
                whileHover="hover"
              >
                <div className="absolute top-4 left-4 font-mono text-[10px] tracking-widest text-white/20 border border-white/5 px-2 py-0.5 rounded-full">STEP {step.step}</div>
                <motion.div
                  className="w-14 h-14 rounded-2xl flex items-center justify-center mb-6 relative z-10 border"
                  style={{ background: `rgba(${step.rgb},0.08)`, borderColor: `rgba(${step.rgb},0.2)`, boxShadow: `0 0 20px rgba(${step.rgb},0.1)` }}
                  animate={{ rotate: [0, 2, -0.5, 0], scale: [1, 1.05, 1] }}
                  transition={{ duration: 4, repeat: Infinity, ease: "easeInOut", delay: i * 0.3 }}
                >
                  <step.icon className="w-7 h-7" style={{ color: step.color }} aria-hidden="true" />
                </motion.div>
                <h3 className="text-xl font-bold text-white tracking-tight mb-4 relative z-10">{step.title}</h3>
                <p className="text-sm leading-relaxed mb-6 flex-grow relative z-10 text-white/50">{step.desc}</p>
                <div className="mt-2 inline-flex items-center px-3 py-1.5 rounded-lg relative z-10 bg-white/[0.03] border border-white/[0.05]">
                  <span className="text-[9px] font-mono uppercase tracking-widest text-white/20">{step.tag}</span>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Meet the Agents ── */}
      <section className="relative py-28 px-6 z-10 border-t border-white/[0.04]">
        <div className="max-w-6xl mx-auto">
          <motion.div className="text-center mb-14" initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.5 }}>
            <p className="text-xs tracking-[0.25em] mb-3 font-mono text-cyan-400/60">THE COUNCIL</p>
            <h2 id="agents-heading" className="text-3xl md:text-5xl font-bold text-white">Meet the Agents</h2>
            <p className="text-base mt-4 max-w-xl mx-auto leading-relaxed text-white/[0.38]">Six specialists with distinct forensic expertise, deliberating as one council.</p>
          </motion.div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {AGENTS.map((agent, i) => (
              <motion.div
                key={agent.id}
                className="rounded-2xl p-8 flex flex-col items-center text-center cursor-default relative border border-white/[0.06] bg-white/[0.025]"
                style={{ backdropFilter: "blur(20px) saturate(150%)", boxShadow: "inset 0 1px 0 rgba(255,255,255,0.05), inset 0 -1px 0 rgba(255,255,255,0.02), 0 4px 24px rgba(0,0,0,0.25)" }}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: i * 0.07 }}
                variants={cardHover}
                whileHover="hover"
              >
                <motion.div
                  className="w-14 h-14 rounded-2xl flex items-center justify-center mb-6 relative z-10 border"
                  style={{ background: `rgba(${agent.bgRgb},0.08)`, borderColor: `rgba(${agent.bgRgb},0.2)`, boxShadow: `0 0 25px rgba(${agent.bgRgb},0.12)` }}
                  animate={{ scale: [1, 1.06, 1] }}
                  transition={{ duration: 5, repeat: Infinity, ease: "easeInOut", delay: i * 0.2 }}
                >
                  <agent.icon className="w-7 h-7" style={{ color: agent.color }} aria-hidden="true" />
                </motion.div>
                <h3 className="text-xl font-bold text-white mb-4 tracking-tight relative z-10">{agent.name}</h3>
                <p className="text-sm leading-relaxed flex-grow relative z-10 text-white/45">{agent.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Example Report ── */}
      <section className="relative py-24 px-6 z-10">
        <div className="max-w-6xl mx-auto">
          <motion.div className="text-center mb-14" initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.5 }}>
            <p className="text-xs tracking-[0.25em] mb-3 font-mono text-cyan-400/60">SAMPLE OUTPUT</p>
            <h2 id="report-heading" className="text-3xl md:text-5xl font-bold text-white">Example Report</h2>
            <p className="text-base mt-4 max-w-xl mx-auto leading-relaxed text-white/[0.38]">A preview of what the Council produces for each evidence type.</p>
          </motion.div>
          <ExampleReportSection />
        </div>
      </section>

      {/* ── Modals ── */}
      <AnimatePresence>
        {showUploadModal && <UploadModal key="upload-modal" onClose={() => setShowUploadModal(false)} onFileSelected={handleFileSelected} />}
        {showSuccessModal && uploadedFile && <UploadSuccessModal key="success-modal" file={uploadedFile} onNewUpload={handleNewUpload} onStartAnalysis={handleStartAnalysis} />}
      </AnimatePresence>
    </div>
  );
}
