"use client";

import { useState, useMemo, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowRight, UploadCloud, X, RefreshCw,
  FileImage, FileAudio, FileVideo,
  Image as ImageIcon, Mic, Crosshair, Video, FileCode2, Scale,
  ShieldCheck, Cpu, FileSignature, CheckCircle, AlertTriangle,
  ChevronDown, Home,
} from "lucide-react";
import { autoLoginAsInvestigator } from "@/lib/api";

// ── Easing ────────────────────────────────────────────────────────────────────
const SPRING = { type: "spring", stiffness: 340, damping: 28 } as const;

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
    name: "Object & Weapon Analyst",
    icon: Crosshair,
    color: "#f59e0b",
    bgRgb: "245,158,11",
    badge: "Contextual Consistency",
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
    desc: "Image Forensics, Audio Forensics, Object & Weapon Analyst, Video Forensics, and Metadata Expert run parallel deep analysis loops.",
    tag: "5 Specialists Active",
    color: "#a78bfa",
    rgb: "167,139,250",
  },
  {
    step: "03",
    icon: Scale,
    title: "Council Deliberation",
    desc: "The Arbiter cross-references all agent findings, resolves conflicts, and synthesises a unified confidence score.",
    tag: "Conflict Resolution",
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
const REPORT_TABS = ["Image Analysis", "Audio Analysis", "Video Analysis"] as const;
type ReportTab = (typeof REPORT_TABS)[number];

const MOCK_REPORTS: Record<ReportTab, {
  file: string;
  verdict: string;
  verdictLabel: string;
  confidence: number;
  agents: { name: string; verdict: string; conf: number; finding: string }[];
  arbiterNote: string;
}> = {
  "Image Analysis": {
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
  "Audio Analysis": {
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
  "Video Analysis": {
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

// ── Microscope Scanner ─────────────────────────────────────────────────────────
function MicroscopeScanner() {
  const size = 260;
  const bracketLen = 26;
  const cyan = "#22d3ee";
  const cyanGlow = "rgba(34,211,238,0.4)";

  return (
    <div
      className="relative select-none"
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      {/* Ambient glow behind scanner */}
      <div
        className="absolute pointer-events-none"
        style={{
          inset: "-30%",
          background: "radial-gradient(ellipse at center, rgba(34,211,238,0.07) 0%, transparent 65%)",
          filter: "blur(24px)",
        }}
      />

      {/* Main scanner frame */}
      <div
        className="absolute inset-0 rounded-2xl overflow-hidden"
        style={{
          background: "rgba(34,211,238,0.015)",
          border: `1px solid rgba(34,211,238,0.25)`,
          boxShadow: `0 0 0 1px rgba(34,211,238,0.05), inset 0 0 40px rgba(34,211,238,0.02)`,
        }}
      >
        {/* Scan beam */}
        <motion.div
          className="absolute left-0 right-0 pointer-events-none"
          style={{
            height: 2,
            background: `linear-gradient(90deg, transparent 0%, ${cyanGlow} 15%, rgba(34,211,238,0.95) 50%, ${cyanGlow} 85%, transparent 100%)`,
            boxShadow: `0 0 10px 3px rgba(34,211,238,0.2), 0 0 30px 6px rgba(34,211,238,0.1)`,
          }}
          initial={{ top: 0, opacity: 0 }}
          animate={{ top: ["-2px", `${size + 2}px`], opacity: [0, 1, 1, 0] }}
          transition={{ duration: 2.4, repeat: Infinity, ease: "linear", times: [0, 0.04, 0.96, 1], repeatDelay: 0.8 }}
        />

        {/* Grid lines */}
        {[0.25, 0.5, 0.75].map((f) => (
          <div key={`h${f}`} className="absolute left-0 right-0" style={{ top: `${f * 100}%`, height: 1, background: "rgba(34,211,238,0.05)" }} />
        ))}
        {[0.25, 0.5, 0.75].map((f) => (
          <div key={`v${f}`} className="absolute top-0 bottom-0" style={{ left: `${f * 100}%`, width: 1, background: "rgba(34,211,238,0.05)" }} />
        ))}

        {/* Reticle */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="relative w-14 h-14">
            <div className="absolute top-1/2 left-0 right-0 h-px" style={{ background: "rgba(34,211,238,0.3)" }} />
            <div className="absolute left-1/2 top-0 bottom-0 w-px" style={{ background: "rgba(34,211,238,0.3)" }} />
            <motion.div
              className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-2 h-2 rounded-full"
              style={{ background: cyan, boxShadow: `0 0 8px 2px ${cyanGlow}` }}
              animate={{ scale: [1, 1.5, 1], opacity: [0.7, 1, 0.7] }}
              transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
            />
          </div>
        </div>

        {/* Detection flare particles */}
        {[
          { x: "28%", y: "33%", delay: 1.1 },
          { x: "67%", y: "57%", delay: 0.5 },
          { x: "19%", y: "68%", delay: 2.0 },
          { x: "74%", y: "26%", delay: 0.2 },
          { x: "48%", y: "78%", delay: 1.5 },
        ].map((p, i) => (
          <motion.div
            key={i}
            className="absolute w-1.5 h-1.5 rounded-full pointer-events-none"
            style={{ left: p.x, top: p.y, background: cyan, boxShadow: `0 0 6px 2px ${cyanGlow}` }}
            initial={{ opacity: 0, scale: 0 }}
            animate={{ opacity: [0, 1, 0], scale: [0, 1.3, 0] }}
            transition={{ duration: 0.5, repeat: Infinity, repeatDelay: 2.4, delay: p.delay }}
          />
        ))}
      </div>

      {/* Corner brackets */}
      {(["tl", "tr", "bl", "br"] as const).map((corner) => (
        <div
          key={corner}
          className="absolute pointer-events-none"
          style={{
            width: bracketLen, height: bracketLen,
            top: corner.startsWith("t") ? 0 : undefined,
            bottom: corner.startsWith("b") ? 0 : undefined,
            left: corner.endsWith("l") ? 0 : undefined,
            right: corner.endsWith("r") ? 0 : undefined,
          }}
        >
          <div
            className="absolute"
            style={{
              [corner.startsWith("t") ? "top" : "bottom"]: 0,
              [corner.endsWith("l") ? "left" : "right"]: 0,
              width: "100%", height: 2,
              background: cyan, boxShadow: `0 0 5px ${cyanGlow}`,
            }}
          />
          <div
            className="absolute"
            style={{
              [corner.startsWith("t") ? "top" : "bottom"]: 0,
              [corner.endsWith("l") ? "left" : "right"]: 0,
              width: 2, height: "100%",
              background: cyan, boxShadow: `0 0 5px ${cyanGlow}`,
            }}
          />
        </div>
      ))}

      {/* Status label */}
      <motion.div
        className="absolute -bottom-9 left-0 right-0 flex items-center justify-center gap-2"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.6 }}
      >
        <motion.div
          className="w-1.5 h-1.5 rounded-full bg-emerald-400"
          animate={{ opacity: [1, 0.3, 1] }}
          transition={{ duration: 1.4, repeat: Infinity }}
        />
        <span
          className="text-[10px] tracking-[0.28em] uppercase"
          style={{ color: "rgba(34,211,238,0.65)", fontFamily: "var(--font-fira-code), monospace" }}
        >
          SCANNING EVIDENCE
        </span>
      </motion.div>
    </div>
  );
}

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
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.7)" }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onClose}
    >
      <motion.div
        className="relative w-full max-w-md rounded-2xl p-8"
        style={{
          background: "rgba(12,16,28,0.94)",
          backdropFilter: "blur(40px) saturate(200%)",
          WebkitBackdropFilter: "blur(40px) saturate(200%)",
          border: "1px solid rgba(255,255,255,0.1)",
          boxShadow: "0 32px 80px rgba(0,0,0,0.8), inset 0 1px 0 rgba(255,255,255,0.09)",
        }}
        initial={{ scale: 0.94, opacity: 0, y: 16 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.94, opacity: 0, y: 16 }}
        transition={SPRING}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-2 rounded-lg cursor-pointer transition-colors"
          style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)" }}
          aria-label="Close upload modal"
        >
          <X className="w-4 h-4 text-white/50" />
        </button>

        <h3 className="text-lg font-bold text-white mb-1">Upload Evidence</h3>
        <p className="text-sm mb-6" style={{ color: "rgba(255,255,255,0.45)" }}>
          Images, audio, and video files up to 50 MB.
        </p>

        <div
          className="rounded-xl border-2 border-dashed p-10 text-center cursor-pointer transition-all duration-200"
          style={{
            borderColor: isDragging ? "rgba(34,211,238,0.5)" : "rgba(255,255,255,0.1)",
            background: isDragging ? "rgba(34,211,238,0.04)" : "transparent",
          }}
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <UploadCloud className="w-9 h-9 mx-auto mb-3" style={{ color: "rgba(34,211,238,0.55)" }} aria-hidden="true" />
          <p className="text-sm font-medium mb-1" style={{ color: "rgba(255,255,255,0.65)" }}>
            Drop file here or <span style={{ color: "#22d3ee" }}>browse</span>
          </p>
          <p className="text-xs" style={{ color: "rgba(255,255,255,0.25)" }}>
            JPG · PNG · MP4 · MOV · WAV · MP3 · max 50 MB
          </p>
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept="image/*,audio/*,video/*"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
          />
        </div>
      </motion.div>
    </motion.div>
  );
}

// ── Upload Success Modal ──────────────────────────────────────────────────────
function UploadSuccessModal({ file, onNewUpload, onStartAnalysis }: {
  file: File;
  onNewUpload: () => void;
  onStartAnalysis: () => void;
}) {
  const previewUrl = useMemo(() => {
    if (file.type.startsWith("image/")) return URL.createObjectURL(file);
    return null;
  }, [file]);

  useEffect(() => {
    return () => { if (previewUrl) URL.revokeObjectURL(previewUrl); };
  }, [previewUrl]);

  const FileTypeIcon = file.type.startsWith("image/") ? FileImage
    : file.type.startsWith("audio/") ? FileAudio
    : FileVideo;

  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.7)" }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <motion.div
        className="relative w-full max-w-sm rounded-2xl p-8 text-center"
        style={{
          background: "rgba(12,16,28,0.94)",
          backdropFilter: "blur(40px) saturate(200%)",
          WebkitBackdropFilter: "blur(40px) saturate(200%)",
          border: "1px solid rgba(255,255,255,0.1)",
          boxShadow: "0 32px 80px rgba(0,0,0,0.8), inset 0 1px 0 rgba(255,255,255,0.09)",
        }}
        initial={{ scale: 0.94, opacity: 0, y: 16 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.94, opacity: 0, y: 16 }}
        transition={SPRING}
      >
        <div
          className="w-20 h-20 rounded-xl mx-auto mb-4 overflow-hidden flex items-center justify-center"
          style={{ background: "rgba(34,211,238,0.06)", border: "1px solid rgba(34,211,238,0.15)" }}
        >
          {previewUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={previewUrl} alt="File preview" className="w-full h-full object-cover" />
          ) : (
            <FileTypeIcon className="w-8 h-8" style={{ color: "rgba(34,211,238,0.55)" }} aria-hidden="true" />
          )}
        </div>

        <div className="flex items-center justify-center gap-2 mb-1">
          <CheckCircle className="w-4 h-4 text-emerald-400" aria-hidden="true" />
          <span className="text-sm font-semibold text-emerald-400">File Ready</span>
        </div>
        <p className="text-xs truncate px-2 mb-6" style={{ color: "rgba(255,255,255,0.4)" }}>{file.name}</p>

        <div className="flex gap-3">
          <button
            onClick={onNewUpload}
            className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-medium cursor-pointer transition-colors"
            style={{
              background: "rgba(255,255,255,0.05)",
              border: "1px solid rgba(255,255,255,0.08)",
              color: "rgba(255,255,255,0.65)",
            }}
          >
            <RefreshCw className="w-4 h-4" aria-hidden="true" />
            New Upload
          </button>
          <button
            onClick={onStartAnalysis}
            className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-semibold cursor-pointer transition-all"
            style={{
              background: "linear-gradient(135deg, #0891b2 0%, #22d3ee 100%)",
              color: "#fff",
              boxShadow: "0 0 24px rgba(34,211,238,0.2)",
            }}
          >
            Start Analysis
            <ArrowRight className="w-4 h-4" aria-hidden="true" />
          </button>
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
        {REPORT_TABS.map((tab, i) => (
          <button
            key={tab}
            onClick={() => setActiveTab(i)}
            className="px-5 py-2 rounded-xl text-sm font-medium cursor-pointer transition-all"
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
            {tab}
          </button>
        ))}
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

// ── Section divider ───────────────────────────────────────────────────────────
const sectionBorder = { borderTop: "1px solid rgba(255,255,255,0.04)" } as const;

// ── Landing Page ──────────────────────────────────────────────────────────────
export default function LandingPage() {
  const router = useRouter();
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [showSuccessModal, setShowSuccessModal] = useState(false);

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
      {/* ── Background scene ── */}
      <div className="fixed inset-0 pointer-events-none" aria-hidden="true">
        <div
          className="absolute"
          style={{
            top: "-8%", left: "12%",
            width: 640, height: 640,
            background: "radial-gradient(circle, rgba(79,70,229,0.2) 0%, transparent 70%)",
            filter: "blur(90px)",
          }}
        />
        <div
          className="absolute"
          style={{
            top: "35%", right: "8%",
            width: 520, height: 520,
            background: "radial-gradient(circle, rgba(13,148,136,0.16) 0%, transparent 70%)",
            filter: "blur(75px)",
          }}
        />
        <div
          className="absolute inset-0"
          style={{
            backgroundImage:
              "linear-gradient(to right, rgba(255,255,255,0.018) 1px, transparent 1px)," +
              "linear-gradient(to bottom, rgba(255,255,255,0.018) 1px, transparent 1px)",
            backgroundSize: "64px 64px",
          }}
        />
      </div>

      {/* ── Navbar ── */}
      <nav
        aria-label="Main navigation"
        className="fixed top-4 left-4 right-4 z-50 flex items-center justify-between px-5 py-3 rounded-2xl"
        style={{
          background: "rgba(12,16,28,0.88)",
          backdropFilter: "blur(40px) saturate(200%)",
          WebkitBackdropFilter: "blur(40px) saturate(200%)",
          border: "1px solid rgba(255,255,255,0.09)",
          boxShadow: "0 8px 32px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.09)",
        }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold"
            style={{
              background: "rgba(34,197,94,0.12)",
              border: "1px solid rgba(34,197,94,0.28)",
              color: "#22d3ee",
              fontFamily: "var(--font-fira-code), monospace",
            }}
          >
            FC
          </div>
          <span className="font-semibold text-white tracking-tight text-sm">Forensic Council</span>
        </div>

        <button
          onClick={() => setShowUploadModal(true)}
          className="hidden md:inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium cursor-pointer transition-colors"
          style={{
            background: "rgba(34,211,238,0.08)",
            border: "1px solid rgba(34,211,238,0.18)",
            color: "#22d3ee",
          }}
        >
          Begin Analysis
          <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
        </button>
      </nav>

      {/* ── Hero ── */}
      <section className="relative min-h-screen flex flex-col items-center justify-center pt-28 pb-24 px-6 text-center">

        {/* Status pill */}
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="inline-flex items-center gap-2 px-4 py-1.5 mb-8 rounded-full text-xs"
          style={{
            background: "rgba(34,197,94,0.06)",
            border: "1px solid rgba(34,197,94,0.2)",
            color: "#22C55E",
            fontFamily: "var(--font-fira-code), monospace",
            letterSpacing: "0.15em",
          }}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" aria-hidden="true" />
          SYSTEM OPERATIONAL
        </motion.div>

        {/* Title */}
        <motion.h1
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.18, duration: 0.65 }}
          className="text-5xl md:text-7xl lg:text-[5.5rem] font-extrabold tracking-tight mb-6 leading-[1.05]"
          style={{
            background: "linear-gradient(160deg, #f8fafc 0%, rgba(248,250,252,0.65) 100%)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            backgroundClip: "text",
          }}
        >
          Forensic Council
        </motion.h1>

        {/* Sub-headline */}
        <motion.p
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.32, duration: 0.55 }}
          className="text-base md:text-lg font-normal mb-10 max-w-2xl leading-relaxed"
          style={{ color: "rgba(248,250,252,0.5)" }}
        >
          A council of five AI specialists —{" "}
          <span style={{ color: "rgba(248,250,252,0.8)" }}>Image Forensics</span>,{" "}
          <span style={{ color: "rgba(248,250,252,0.8)" }}>Audio Forensics</span>,{" "}
          <span style={{ color: "rgba(248,250,252,0.8)" }}>Object & Weapon Analyst</span>,{" "}
          <span style={{ color: "rgba(248,250,252,0.8)" }}>Video Forensics</span>,{" "}
          <span style={{ color: "rgba(248,250,252,0.8)" }}>Metadata Expert</span>{" "}
          — deliberate and deliver one cryptographically signed verdict.
        </motion.p>

        {/* Microscope scanner */}
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.42, duration: 0.65 }}
          className="mb-14"
        >
          <MicroscopeScanner />
        </motion.div>

        {/* CTA row */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.58, duration: 0.45 }}
          className="flex flex-col sm:flex-row gap-4 items-center"
        >
          <button
            onClick={() => setShowUploadModal(true)}
            className="group inline-flex items-center gap-3 px-7 py-3.5 rounded-2xl text-sm font-semibold cursor-pointer transition-all duration-200"
            style={{
              background: "linear-gradient(135deg, #0891b2 0%, #22d3ee 100%)",
              color: "#fff",
              boxShadow: "0 0 40px rgba(34,211,238,0.18), inset 0 1px 0 rgba(255,255,255,0.15)",
            }}
          >
            <UploadCloud className="w-4 h-4" aria-hidden="true" />
            Upload Evidence
          </button>
          <Link
            href="/evidence"
            className="inline-flex items-center gap-2 px-6 py-3.5 rounded-2xl text-sm font-medium cursor-pointer transition-all duration-200"
            style={{
              background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.09)",
              color: "rgba(255,255,255,0.65)",
            }}
          >
            Open Investigation Lab
            <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
          </Link>
        </motion.div>
      </section>

      {/* ── How It Works ── */}
      <section className="relative py-24 px-6 z-10" aria-labelledby="how-it-works-heading" style={sectionBorder}>
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <p className="text-xs tracking-[0.25em] mb-3 font-mono" style={{ color: "rgba(34,211,238,0.6)" }}>
              PROCESS
            </p>
            <h2 id="how-it-works-heading" className="text-3xl md:text-5xl font-bold text-white">
              How It Works
            </h2>
            <p className="text-base mt-4 max-w-xl mx-auto leading-relaxed" style={{ color: "rgba(255,255,255,0.38)" }}>
              From upload to signed verdict in four automated steps.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
            {HOW_IT_WORKS.map((step, i) => (
              <motion.div
                key={step.step}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-40px" }}
                transition={{ delay: i * 0.09 }}
                className="relative rounded-2xl p-6"
                style={{
                  background: "rgba(255,255,255,0.035)",
                  backdropFilter: "blur(16px)",
                  WebkitBackdropFilter: "blur(16px)",
                  border: "1px solid rgba(255,255,255,0.065)",
                  boxShadow: "inset 0 1px 0 rgba(255,255,255,0.06)",
                }}
              >
                <div
                  className="w-11 h-11 rounded-xl flex items-center justify-center mb-5"
                  style={{
                    background: `rgba(${step.rgb},0.1)`,
                    border: `1px solid rgba(${step.rgb},0.2)`,
                  }}
                >
                  <step.icon className="w-5 h-5" style={{ color: step.color }} aria-hidden="true" />
                </div>
                <p className="text-[10px] font-mono font-bold tracking-widest mb-2" style={{ color: `${step.color}80` }}>
                  STEP {step.step}
                </p>
                <h3 className="font-bold text-white mb-3">{step.title}</h3>
                <p className="text-sm leading-relaxed" style={{ color: "rgba(255,255,255,0.48)" }}>{step.desc}</p>
                <div
                  className="mt-4 inline-flex items-center px-2.5 py-1 rounded-lg"
                  style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)" }}
                >
                  <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: "rgba(255,255,255,0.28)" }}>
                    {step.tag}
                  </span>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Meet the Agents ── */}
      <section className="relative py-24 px-6 z-10" aria-labelledby="agents-heading" style={sectionBorder}>
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

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {AGENTS.map((agent, i) => (
              <motion.div
                key={agent.id}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-40px" }}
                transition={{ delay: i * 0.07 }}
                whileHover={{ scale: 1.015, transition: { duration: 0.15 } }}
                className="relative rounded-2xl p-6 cursor-default"
                style={{
                  background: "rgba(255,255,255,0.035)",
                  backdropFilter: "blur(16px)",
                  WebkitBackdropFilter: "blur(16px)",
                  border: "1px solid rgba(255,255,255,0.065)",
                  boxShadow: "inset 0 1px 0 rgba(255,255,255,0.06)",
                }}
              >
                <div
                  className="w-12 h-12 rounded-xl flex items-center justify-center mb-5"
                  style={{
                    background: `rgba(${agent.bgRgb},0.1)`,
                    border: `1px solid rgba(${agent.bgRgb},0.2)`,
                  }}
                >
                  <agent.icon className="w-6 h-6" style={{ color: agent.color }} aria-hidden="true" />
                </div>
                <p className="text-[10px] font-mono font-bold tracking-widest mb-1" style={{ color: `${agent.color}65` }}>
                  {agent.id}
                </p>
                <h3 className="font-bold text-white mb-1">{agent.name}</h3>
                <p className="text-[11px] font-mono mb-3" style={{ color: `${agent.color}85` }}>{agent.badge}</p>
                <p className="text-sm leading-relaxed" style={{ color: "rgba(255,255,255,0.48)" }}>{agent.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Example Report ── */}
      <section className="relative py-24 px-6 z-10" aria-labelledby="example-report-heading" style={sectionBorder}>
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <p className="text-xs tracking-[0.25em] mb-3 font-mono" style={{ color: "rgba(34,211,238,0.6)" }}>
              SAMPLE OUTPUT
            </p>
            <h2 id="example-report-heading" className="text-3xl md:text-5xl font-bold text-white">
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
    </div>
  );
}
