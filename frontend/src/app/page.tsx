"use client";

import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import {
  ChevronRight, ShieldCheck, File, UploadCloud,
  FileImage, FileAudio, FileVideo, X, ArrowRight, RotateCcw,
} from "lucide-react";
import { useEffect, useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { AGENTS_DATA, ALLOWED_MIME_TYPES } from "@/lib/constants";
import { AgentIcon } from "@/components/ui/AgentIcon";
import { GlobalFooter } from "@/components/ui/GlobalFooter";
import { useSound } from "@/hooks/useSound";

/* ─── Microscope Scanner ─────────────────────────────────────────────────── */
function MicroscopeScanner() {
  const reduced = useReducedMotion();

  // Specimen cells scattered across the field of view
  const SPECIMENS = [
    { pos: "left-[19%] top-[22%]",  delay: 0.6  },
    { pos: "right-[17%] top-[19%]", delay: 1.4  },
    { pos: "left-[15%] bottom-[24%]", delay: 2.1 },
    { pos: "right-[20%] bottom-[27%]", delay: 0.9 },
    { pos: "left-[43%] top-[14%]",  delay: 1.7  },
    { pos: "right-[38%] bottom-[15%]", delay: 2.8 },
  ];

  // Primary cyan data tags (cycle in)
  const TAGS_A = [
    { label: "ELA",  val: "0.023",   x: "left-[7%]",   y: "top-[37%]",    delay: 0   },
    { label: "PRNU", val: "MATCH",   x: "right-[6%]",  y: "top-[43%]",    delay: 0.9 },
    { label: "GPS",  val: "34.05°N", x: "left-[8%]",   y: "bottom-[33%]", delay: 0.5 },
    { label: "SHA",  val: "a9f2…",   x: "right-[7%]",  y: "bottom-[29%]", delay: 1.3 },
  ];

  // Violet data tags (offset timing)
  const TAGS_B = [
    { label: "DFT",  val: "−42dB",   x: "left-[14%]",  y: "top-[16%]",    delay: 2.0 },
    { label: "META", val: "INTACT",  x: "right-[13%]", y: "top-[18%]",    delay: 2.6 },
    { label: "HASH", val: "VALID",   x: "left-[12%]",  y: "bottom-[17%]", delay: 1.8 },
    { label: "FFT",  val: "0.91",    x: "right-[11%]", y: "bottom-[21%]", delay: 3.1 },
  ];

  return (
    <div className="absolute inset-0 flex items-center justify-center pointer-events-none" aria-hidden="true">

      {/* Deep atmosphere — outer depth blur */}
      <div className="absolute w-[920px] h-[920px] rounded-full"
        style={{ background: "radial-gradient(circle, rgba(0,212,255,0.022) 0%, transparent 58%)", filter: "blur(32px)" }} />
      <div className="absolute w-[640px] h-[640px] rounded-full"
        style={{ background: "radial-gradient(circle, rgba(0,212,255,0.048) 0%, transparent 62%)" }} />

      {/* Main viewport container */}
      <div className="relative w-[580px] h-[580px]">

        {/* Ring 0 — far outer atmosphere */}
        <div className="absolute inset-0 rounded-full border border-cyan-500/7"
          style={{ boxShadow: "inset 0 0 90px rgba(0,212,255,0.018)" }} />

        {/* Ring 1 — outer static rim */}
        <div className="absolute inset-[18px] rounded-full border border-cyan-500/12" />

        {/* Ring 2 — dashed slow CW with tick marks */}
        <div
          className="absolute inset-[58px] rounded-full border border-dashed border-cyan-400/18"
          style={{ animation: reduced ? "none" : "ring-spin-slow 58s linear infinite" }}
        />

        {/* Ring 3 — medium CCW */}
        <div
          className="absolute inset-[115px] rounded-full border border-cyan-500/22"
          style={{ animation: reduced ? "none" : "ring-spin-reverse 32s linear infinite" }}
        />

        {/* Ring 4 — inner field ring */}
        <div
          className="absolute inset-[178px] rounded-full border-2 border-cyan-400/14"
          style={{ animation: reduced ? "none" : "ring-spin-slow 20s linear infinite reverse" }}
        />

        {/* Ring 5 — innermost focus ring pulsing */}
        <div
          className="absolute inset-[228px] rounded-full border border-cyan-400/38"
          style={{ animation: reduced ? "none" : "pulse-ring 3.5s ease-in-out infinite" }}
        />

        {/* Measurement grid — visible inside inner field ring */}
        <div className="absolute inset-[118px] rounded-full overflow-hidden opacity-[0.18]">
          <div className="absolute inset-0"
            style={{
              backgroundImage: "linear-gradient(rgba(0,212,255,0.3) 1px, transparent 1px), linear-gradient(90deg, rgba(0,212,255,0.3) 1px, transparent 1px)",
              backgroundSize: "28px 28px",
            }}
          />
        </div>

        {/* Crosshair — main axes */}
        <div className="absolute top-1/2 left-0 right-0 h-px bg-gradient-to-r from-transparent via-cyan-400/28 to-transparent -translate-y-1/2" />
        <div className="absolute left-1/2 top-0 bottom-0 w-px bg-gradient-to-b from-transparent via-cyan-400/28 to-transparent -translate-x-1/2" />

        {/* 45° diagonal tics at outer ring */}
        <div className="absolute inset-[58px] rounded-full overflow-hidden pointer-events-none opacity-20">
          <div className="absolute top-1/2 left-0 right-0 h-px bg-gradient-to-r from-transparent via-cyan-400/50 to-transparent -translate-y-1/2 rotate-45 scale-x-[1.4]" />
          <div className="absolute top-1/2 left-0 right-0 h-px bg-gradient-to-r from-transparent via-cyan-400/50 to-transparent -translate-y-1/2 -rotate-45 scale-x-[1.4]" />
        </div>

        {/* Corner reticle brackets — outer */}
        {[
          "top-[57px] left-[57px] border-t-2 border-l-2",
          "top-[57px] right-[57px] border-t-2 border-r-2",
          "bottom-[57px] left-[57px] border-b-2 border-l-2",
          "bottom-[57px] right-[57px] border-b-2 border-r-2",
        ].map((cls, i) => (
          <div key={i} className={`absolute w-6 h-6 border-cyan-400/48 ${cls}`} />
        ))}

        {/* Corner reticle brackets — inner field ring */}
        {[
          "top-[178px] left-[178px] border-t border-l",
          "top-[178px] right-[178px] border-t border-r",
          "bottom-[178px] left-[178px] border-b border-l",
          "bottom-[178px] right-[178px] border-b border-r",
        ].map((cls, i) => (
          <div key={i} className={`absolute w-4 h-4 border-cyan-400/30 ${cls}`} />
        ))}

        {/* Specimen cells — evidence particles in the field */}
        {SPECIMENS.map((s, i) => (
          <motion.div
            key={i}
            className={`absolute ${s.pos}`}
            initial={{ opacity: 0 }}
            animate={reduced ? {} : { opacity: [0, 0.55, 0.72, 0.45, 0.60] }}
            transition={{ delay: s.delay, duration: 3.6 + i * 0.45, repeat: Infinity }}
          >
            <div className="w-3.5 h-3.5 rounded-full border border-cyan-400/45 flex items-center justify-center"
              style={{ boxShadow: "0 0 7px rgba(0,212,255,0.32)" }}>
              <div className="w-1.5 h-1.5 rounded-full bg-cyan-300/62" />
            </div>
          </motion.div>
        ))}

        {/* Core specimen — primary target with selection ring */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-10">
          <motion.div
            className="absolute -inset-5 rounded-full border border-cyan-400/30"
            animate={reduced ? {} : { scale: [1, 1.10, 1], opacity: [0.30, 0.58, 0.30] }}
            transition={{ duration: 2.8, repeat: Infinity, ease: "easeInOut" }}
          />
          <div
            className="w-3 h-3 rounded-full bg-cyan-400"
            style={{
              boxShadow: "0 0 18px rgba(0,212,255,0.95), 0 0 36px rgba(0,212,255,0.35)",
              animation: reduced ? "none" : "scan-glow 2s ease-in-out infinite",
            }}
          />
        </div>

        {/* Horizontal scan beam — wide glow sweep */}
        {!reduced && (
          <motion.div
            animate={{ left: ["-18%", "118%"] }}
            transition={{ duration: 3.8, ease: "easeInOut", repeat: Infinity, repeatDelay: 2.2 }}
            className="absolute top-[16%] bottom-[16%] w-[210px] pointer-events-none"
            style={{
              background: "linear-gradient(to right, transparent, rgba(0,212,255,0.035), rgba(0,212,255,0.075), rgba(0,212,255,0.035), transparent)",
              filter: "blur(3px)",
            }}
          />
        )}

        {/* Vertical scan line — sharp with glow trail */}
        {!reduced && (
          <motion.div
            animate={{ top: ["18%", "82%", "18%"] }}
            transition={{ duration: 4.4, ease: "linear", repeat: Infinity }}
            className="absolute left-[18%] right-[18%] h-[2px] pointer-events-none"
            style={{
              background: "linear-gradient(to right, transparent, rgba(0,212,255,0.65), transparent)",
              boxShadow: "0 0 10px rgba(0,212,255,0.52), 0 0 22px rgba(0,212,255,0.18)",
            }}
          />
        )}

        {/* Secondary violet scan sweep — offset timing, RTL */}
        {!reduced && (
          <motion.div
            animate={{ left: ["118%", "-18%"] }}
            transition={{ duration: 5.8, ease: "easeInOut", repeat: Infinity, repeatDelay: 1.2, delay: 2.8 }}
            className="absolute top-[28%] bottom-[28%] w-[160px] pointer-events-none"
            style={{
              background: "linear-gradient(to right, transparent, rgba(124,58,237,0.035), rgba(124,58,237,0.055), rgba(124,58,237,0.035), transparent)",
              filter: "blur(2px)",
            }}
          />
        )}

        {/* Data readout tags — cyan set */}
        {TAGS_A.map((tag, i) => (
          <motion.div
            key={`a${i}`}
            initial={{ opacity: 0 }}
            animate={reduced ? {} : { opacity: [0, 0.82, 0.82, 0] }}
            transition={{ delay: tag.delay, duration: 5.2, repeat: Infinity, repeatDelay: 2.2 }}
            className={`absolute ${tag.x} ${tag.y} font-mono text-[10px] text-cyan-400/88
              bg-black/80 border border-cyan-500/28 px-2.5 py-1 rounded-lg backdrop-blur-sm
              shadow-[0_0_14px_rgba(0,212,255,0.13)]`}
          >
            <span className="text-cyan-500/52 mr-1.5">{tag.label}</span>{tag.val}
          </motion.div>
        ))}

        {/* Data readout tags — violet set (delayed) */}
        {TAGS_B.map((tag, i) => (
          <motion.div
            key={`b${i}`}
            initial={{ opacity: 0 }}
            animate={reduced ? {} : { opacity: [0, 0, 0.72, 0.72, 0] }}
            transition={{ delay: tag.delay, duration: 4.8, repeat: Infinity, repeatDelay: 3.8 }}
            className={`absolute ${tag.x} ${tag.y} font-mono text-[10px] text-violet-400/82
              bg-black/80 border border-violet-500/25 px-2.5 py-1 rounded-lg backdrop-blur-sm
              shadow-[0_0_12px_rgba(124,58,237,0.10)]`}
          >
            <span className="text-violet-500/48 mr-1.5">{tag.label}</span>{tag.val}
          </motion.div>
        ))}
      </div>

      {/* Radial vignette — fades scanner into hero content */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,rgba(3,3,8,0.97)_70%)]" />
    </div>
  );
}

/* ─── Envelope CTA Animation ─────────────────────────────────────────────── */
type EnvelopePhase = "idle" | "opening" | "open" | "closing";

function EnvelopeCTA({
  onOpen,
  phase,
}: {
  onOpen: () => void;
  phase: EnvelopePhase;
}) {
  return (
    <div className="relative inline-block" style={{ perspective: "800px" }}>
      <motion.button
        onClick={onOpen}
        disabled={phase !== "idle"}
        whileHover={phase === "idle" ? { scale: 1.04 } : {}}
        whileTap={phase === "idle" ? { scale: 0.97 } : {}}
        className="group relative px-10 py-5 rounded-full font-bold text-lg text-white
          bg-gradient-to-r from-emerald-500 to-cyan-500
          border border-white/20 overflow-hidden inline-flex items-center gap-3
          hover:shadow-[0_0_60px_rgba(16,185,129,0.5)]
          focus-visible:ring-4 focus-visible:ring-cyan-500 focus-visible:outline-none
          disabled:pointer-events-none transition-shadow duration-300"
      >
        {/* Shimmer sweep */}
        <div className="absolute inset-y-0 left-0 w-1/2 bg-gradient-to-r from-transparent via-white/15 to-transparent
          opacity-0 group-hover:opacity-100 transition-opacity"
          style={{ animation: "shimmer 0.8s ease-out" }} />

        {/* Envelope icon that flap-opens */}
        <div className="relative w-6 h-5" style={{ transformStyle: "preserve-3d" }}>
          {/* Envelope body */}
          <svg viewBox="0 0 24 18" className="w-6 h-5 absolute inset-0" fill="none">
            <rect x="1" y="4" width="22" height="14" rx="2" fill="rgba(255,255,255,0.2)" stroke="rgba(255,255,255,0.6)" strokeWidth="1.5" />
            <path d="M1 4 L12 11 L23 4" stroke="rgba(255,255,255,0.6)" strokeWidth="1.5" fill="none" />
          </svg>
          {/* Flap — rotates open on hover/phase */}
          <motion.div
            className="absolute inset-x-0 top-0 origin-top"
            style={{ transformStyle: "preserve-3d" }}
            animate={phase === "opening" || phase === "open" ? { rotateX: -180 } : { rotateX: 0 }}
            transition={{ duration: 0.45, ease: [0.34, 1.56, 0.64, 1] }}
          >
            <svg viewBox="0 0 24 9" className="w-6 h-[18px]" fill="none">
              <path d="M1 4 L12 11 L23 4 L22 2 L1 2 Z" fill="rgba(16,185,129,0.7)" stroke="rgba(255,255,255,0.5)" strokeWidth="1.2" />
            </svg>
          </motion.div>
        </div>

        <span className="relative z-10">
          {phase === "idle" || phase === "closing" ? "Begin Analysis" : "Opening…"}
        </span>

        <ChevronRight className="w-5 h-5 group-hover:translate-x-1 transition-transform relative z-10" />
      </motion.button>
    </div>
  );
}

/* ─── Glass card ─────────────────────────────────────────────────────────── */
function GlassCard({
  children,
  className = "",
  glowColor = "cyan",
}: {
  children: React.ReactNode;
  className?: string;
  glowColor?: "cyan" | "violet" | "emerald";
}) {
  const glowMap = {
    cyan:    "hover:border-cyan-400/32 hover:shadow-[0_0_52px_rgba(0,212,255,0.10),0_4px_24px_rgba(0,0,0,0.4),inset_0_1px_0_rgba(0,212,255,0.08)]",
    violet:  "hover:border-violet-400/42 hover:shadow-[0_0_60px_rgba(124,58,237,0.18),0_4px_24px_rgba(0,0,0,0.45),inset_0_1px_0_rgba(168,85,247,0.12)]",
    emerald: "hover:border-emerald-400/32 hover:shadow-[0_0_52px_rgba(16,185,129,0.10),0_4px_24px_rgba(0,0,0,0.4)]",
  }[glowColor];

  return (
    <div
      className={`glass-panel rounded-3xl transition-all duration-500 ease-out
        ${glowMap} ${className}`}
    >
      {children}
    </div>
  );
}

/* ─── Main page ──────────────────────────────────────────────────────────── */
export default function LandingPage() {
  const { playSound } = useSound();
  const router = useRouter();
  const [modalOpen, setModalOpen] = useState(false);
  const [envPhase, setEnvPhase] = useState<EnvelopePhase>("idle");
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback((f: File) => {
    if (f.size > 50 * 1024 * 1024) {
      setValidationError("File must be under 50 MB");
      playSound("error"); return;
    }
    if (!ALLOWED_MIME_TYPES.has(f.type)) {
      setValidationError(`"${f.type || "unknown"}" is not supported. Upload an image, video, or audio file.`);
      playSound("error"); return;
    }
    setValidationError(null);
    setFile(f);
    if (f.type.startsWith("image/") || f.type.startsWith("video/")) {
      setPreviewUrl(URL.createObjectURL(f));
    } else {
      setPreviewUrl(null);
    }
    playSound("success");
  }, [playSound]);

  const handleClearFile = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(null); setPreviewUrl(null); setValidationError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleCTAClick = () => {
    if (envPhase !== "idle") return;
    playSound("envelope_open");
    setEnvPhase("opening");
    setTimeout(() => {
      setEnvPhase("open");
      setModalOpen(true);
    }, 500);
  };

  const handleModalClose = () => {
    playSound("envelope_close");
    setEnvPhase("closing");
    setModalOpen(false);
    handleClearFile();
    setTimeout(() => setEnvPhase("idle"), 400);
  };

  const [isTransitioning, setIsTransitioning] = useState(false);

  const handleInitiate = () => {
    if (!file || isTransitioning) return;
    setIsTransitioning(true);
    playSound("envelope_close");
    setEnvPhase("closing");
    sessionStorage.setItem("forensic_pending_file_name", file.name);
    sessionStorage.setItem("forensic_auto_start", "true");
    (window as { __forensic_pending_file?: File }).__forensic_pending_file = file;
    setTimeout(() => router.push("/evidence"), 380);
  };

  useEffect(() => {
    return () => { if (previewUrl) URL.revokeObjectURL(previewUrl); };
  }, [previewUrl]);

  useEffect(() => { window.scrollTo(0, 0); }, []);

  return (
    <div className="relative bg-[#030308] text-white overflow-x-hidden" style={{ fontFamily: "var(--font-sans), sans-serif" }}>

      {/* ── Background grid + blobs ── */}
      <div className="fixed inset-0 z-0 pointer-events-none">
        {/* Subtle dot grid */}
        <div className="absolute inset-0 bg-[radial-gradient(circle,#ffffff06_1px,transparent_1px)] bg-[size:36px_36px]" />
        {/* Main cyan halo */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[1000px] h-[640px] bg-cyan-900/18 rounded-full blur-[140px]" />
        {/* Violet depth blob */}
        <div className="absolute bottom-0 right-0 w-[560px] h-[560px] bg-violet-900/12 rounded-full blur-[120px]" />
        {/* Subtle indigo accent */}
        <div className="absolute top-[30%] left-0 w-[400px] h-[400px] bg-indigo-900/8 rounded-full blur-[100px]" />
      </div>

      {/* ── Header ── */}
      <header className="fixed top-0 w-full px-6 py-4 flex items-center justify-between
        border-b border-white/[0.05] bg-[#030308]/80 backdrop-blur-2xl z-50">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-gradient-to-br from-cyan-400 to-violet-600 rounded-lg flex items-center justify-center
            font-bold text-[#030308] text-sm shadow-[0_0_20px_rgba(0,212,255,0.3)]"
            style={{ fontFamily: "var(--font-sans)" }}>FC</div>
          <span className="text-lg font-bold tracking-tight bg-gradient-to-r from-white to-slate-400 bg-clip-text text-transparent">
            Forensic Council
          </span>
        </div>
        <span className="text-[10px] font-mono text-slate-600 hidden sm:block">ACADEMIC RESEARCH PROJECT</span>
      </header>

      {/* ══════════════════════════════════════════════════════════
          HERO
      ══════════════════════════════════════════════════════════ */}
      <section className="relative w-full min-h-screen flex flex-col items-center justify-center px-6 pt-20 z-10 overflow-hidden">
        <MicroscopeScanner />

        <div className="relative z-30 flex flex-col items-center text-center max-w-4xl mx-auto">
          {/* Status pill */}
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.7 }}
            className="mb-8 inline-flex items-center gap-2.5 px-4 py-2 rounded-full
              bg-white/[0.05] border border-white/[0.10] text-sm text-cyan-400 backdrop-blur-md"
          >
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-70" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500" />
            </span>
            <span style={{ fontFamily: "var(--font-mono), monospace" }}>System Online — All Agents Ready</span>
          </motion.div>

          {/* Headline */}
          <motion.h1
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.9, ease: "easeOut" }}
            className="text-5xl sm:text-6xl md:text-7xl font-extrabold mb-6 tracking-tight
              text-transparent bg-clip-text bg-gradient-to-b from-white via-white to-slate-400
              leading-[1.05] pb-1"
          >
            Multi-Agent Forensic Evidence Analysis
          </motion.h1>

          {/* Sub */}
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.25, duration: 0.8 }}
            className="text-slate-400 text-lg sm:text-xl max-w-2xl mb-12 leading-relaxed font-normal text-justify-section"
          >
            Five specialist AI agents independently examine your evidence — pixel integrity, audio authenticity,
            object detection, temporal analysis, and metadata provenance — then the Council Arbiter synthesises
            a cryptographically-signed forensic verdict.
          </motion.p>

          {/* CTA */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.45 }}>
            <EnvelopeCTA onOpen={handleCTAClick} phase={envPhase} />
          </motion.div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════════
          HOW IT WORKS
      ══════════════════════════════════════════════════════════ */}
      <section className="relative z-10 py-32 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-20">
            <p className="text-xs font-mono text-cyan-500/70 uppercase tracking-[0.25em] mb-3">Process</p>
            <h2 className="text-4xl md:text-5xl font-bold text-white">How Forensic Council Works</h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 relative">
            {/* Connector line */}
            <div className="hidden md:block absolute top-[72px] left-[12%] right-[12%] h-px
              bg-gradient-to-r from-transparent via-cyan-500/30 to-transparent" />

            {[
              { step: "01", title: "Evidence Intake",     desc: "Upload digital media artifacts — CCTV footage, photographs, audio recordings, or raw metadata exports from field devices." },
              { step: "02", title: "Agent Consultation",  desc: "Five specialist agents process the evidence stream concurrently and independently, each identifying anomalies within their forensic domain." },
              { step: "03", title: "Arbiter Synthesis",   desc: "The Council Arbiter cross-references all findings, resolves contradictions via challenge loops, and computes calibrated confidence scores." },
              { step: "04", title: "Signed Verdict",      desc: "A cryptographically signed forensic report is generated with a five-tier authenticity verdict, chain-of-custody log, and uncertainty statement." },
            ].map((item, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 36 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-60px" }}
                transition={{ delay: i * 0.10, duration: 0.60, ease: [0.22, 1, 0.36, 1] }}
              >
                <GlassCard className="p-8 flex flex-col items-center text-center mt-8 group hover:scale-[1.01]">
                  {/* Step bubble */}
                  <div className="absolute -top-9 w-[68px] h-[68px] rounded-full bg-[#030308]
                    border border-cyan-500/35 flex items-center justify-center
                    font-mono text-xl text-cyan-400 font-bold
                    shadow-[0_0_24px_rgba(0,212,255,0.18)] group-hover:scale-110 transition-transform">
                    {item.step}
                  </div>
                  <h3 className="text-lg font-bold text-white mt-7 mb-3 text-center">{item.title}</h3>
                  <p className="text-slate-400 text-sm leading-relaxed text-justify-section">{item.desc}</p>
                </GlassCard>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════════
          MEET THE COUNCIL
      ══════════════════════════════════════════════════════════ */}
      <section className="relative z-10 pb-32 pt-8 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <p className="text-xs font-mono text-violet-400/70 uppercase tracking-[0.25em] mb-3">Council Members</p>
            <h2 className="text-4xl md:text-5xl font-bold mb-5
              bg-gradient-to-r from-cyan-300 to-violet-300 bg-clip-text text-transparent inline-block">
              Meet the Council
            </h2>
            <p className="text-slate-400 text-lg max-w-2xl mx-auto leading-relaxed text-justify-section">
              Five specialist agents analyse evidence independently, then the Council Arbiter synthesises
              their findings into a unified verdict with confidence scoring.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {AGENTS_DATA.map((agent, i) => (
              <motion.div
                key={agent.id}
                initial={{ opacity: 0, y: 40 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-80px" }}
                transition={{ delay: i * 0.09, duration: 0.6 }}
                whileHover={{ y: -6, scale: 1.015 }}
              >
                <GlassCard className="p-7 flex flex-col items-center text-center h-full group overflow-hidden">
                  {/* Subtle colour tint overlay */}
                  <div className="absolute inset-0 rounded-3xl bg-gradient-to-b from-cyan-500/[0.025] to-transparent pointer-events-none" />

                  <div className="p-4 bg-cyan-500/10 text-cyan-400 rounded-2xl mb-5
                    shadow-[inset_0_0_20px_rgba(0,212,255,0.06)] border border-cyan-500/20
                    relative z-10 group-hover:scale-110 transition-transform duration-400">
                    <AgentIcon role={agent.role} />
                  </div>

                  <h3 className="text-lg font-bold text-white mb-1.5 relative z-10 text-center">{agent.name}</h3>
                  <span className="text-[10px] px-3 py-1 rounded-full bg-cyan-950/60 text-cyan-300
                    border border-cyan-500/20 uppercase tracking-widest font-semibold mb-4 relative z-10">
                    {agent.role}
                  </span>
                  <p className="text-sm text-slate-400 leading-relaxed mb-5 relative z-10 flex-1 text-justify-section">
                    {agent.desc}
                  </p>
                  <div className="w-full pt-4 border-t border-white/[0.06] relative z-10">
                    <p className="text-[11px] text-cyan-400/80 italic leading-relaxed" style={{ fontFamily: "var(--font-mono), monospace" }}>
                      &quot;{agent.simulation.thinking}&quot;
                    </p>
                  </div>
                </GlassCard>
              </motion.div>
            ))}

            {/* Council Arbiter Card */}
            <motion.div
              initial={{ opacity: 0, y: 40 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{ delay: 0.5, duration: 0.6 }}
              whileHover={{ y: -6, scale: 1.015 }}
            >
              <GlassCard
                glowColor="violet"
                className="p-7 flex flex-col items-center text-center h-full group overflow-hidden
                  border-violet-500/25 bg-gradient-to-br from-violet-500/[0.06] to-transparent"
              >
                <div className="absolute inset-0 rounded-3xl bg-[radial-gradient(circle_at_top_right,rgba(124,58,237,0.12),transparent_60%)] pointer-events-none" />

                <div className="p-4 bg-violet-500/20 text-violet-300 rounded-2xl mb-5
                  shadow-[inset_0_0_20px_rgba(124,58,237,0.1)] border border-violet-500/30
                  relative z-10 group-hover:scale-110 transition-transform duration-400">
                  <ShieldCheck className="w-8 h-8" />
                </div>

                <h3 className="text-lg font-bold text-white mb-1.5 relative z-10 text-center
                  drop-shadow-[0_0_12px_rgba(124,58,237,0.6)]">Council Arbiter</h3>
                <span className="text-[10px] px-3 py-1 rounded-full bg-violet-900/60 text-violet-300
                  border border-violet-500/30 uppercase tracking-widest font-bold mb-4 relative z-10">
                  Final Verdict
                </span>
                <p className="text-sm text-slate-400 leading-relaxed mb-5 relative z-10 flex-1 text-justify-section">
                  Cross-references all agent findings, resolves contradictions via challenge loops and tribunal
                  escalation, and produces a cryptographically signed forensic report with a calibrated confidence score.
                </p>
                <div className="w-full pt-4 border-t border-violet-500/20 relative z-10">
                  <p className="text-[11px] text-violet-300/80 italic leading-relaxed" style={{ fontFamily: "var(--font-mono), monospace" }}>
                    &quot;Synthesising cross-modal evidence and resolving logical conflicts…&quot;
                  </p>
                </div>
              </GlassCard>
            </motion.div>
          </div>
        </div>
      </section>

      {/* ── Global Footer ── */}
      <GlobalFooter />

      {/* ══════════════════════════════════════════════════════════
          UPLOAD MODAL — with envelope open/close animation
      ══════════════════════════════════════════════════════════ */}
      <AnimatePresence>
        {modalOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="fixed inset-0 z-[200] flex items-center justify-center p-4"
            onClick={(e) => { if (e.target === e.currentTarget) handleModalClose(); }}
          >
            {/* Backdrop */}
            <div className="absolute inset-0 bg-black/75 backdrop-blur-2xl" />

            <motion.div
              initial={{ scale: 0.88, opacity: 0, y: 32 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.92, opacity: 0, y: 20 }}
              transition={{ type: "spring", stiffness: 300, damping: 28 }}
              className="relative w-full max-w-xl z-10 glass-panel rounded-[2rem] overflow-hidden border-white/10"
              style={{ boxShadow: "0 40px 100px rgba(0,0,0,0.85), 0 0 80px rgba(0,212,255,0.06), inset 0 1px 0 rgba(255,255,255,0.12)" }}
            >
              {/* Envelope opening reveal — content slides up from "inside" */}
              <motion.div
                initial={{ y: 30, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ delay: 0.12, duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
              >
                {/* Modal header */}
                <div className="px-8 pt-8 pb-5 flex items-start justify-between border-b border-white/[0.06]">
                  <div>
                    <div className="flex items-center gap-3 mb-1">
                      <div className="w-8 h-8 rounded-xl bg-cyan-500/20 border border-cyan-500/30
                        flex items-center justify-center">
                        <UploadCloud className="w-4 h-4 text-cyan-400" />
                      </div>
                      <h2 className="text-xl font-bold text-white">Evidence Intake</h2>
                    </div>
                    <p className="text-slate-500 text-sm ml-11">Submit a digital artifact for council analysis</p>
                  </div>
                  <button
                    onClick={handleModalClose}
                    className="p-2 text-slate-500 hover:text-white hover:bg-white/10 rounded-xl transition-colors"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>

                {/* Modal body */}
                <div className="px-8 pb-8 pt-6">
                  <AnimatePresence mode="wait">
                    {!file ? (
                      /* ── DROP ZONE ── */
                      <motion.div key="dz" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}>
                        <input
                          type="file"
                          ref={fileInputRef}
                          className="hidden"
                          accept="image/*,video/*,audio/*"
                          onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
                        />
                        <div
                          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                          onDragLeave={() => setIsDragging(false)}
                          onDrop={(e) => { e.preventDefault(); setIsDragging(false); e.dataTransfer.files?.[0] && handleFile(e.dataTransfer.files[0]); }}
                          onClick={() => fileInputRef.current?.click()}
                          className={`relative cursor-pointer rounded-2xl border-2 border-dashed
                            flex flex-col items-center justify-center py-14 px-8 text-center
                            transition-all duration-300 group overflow-hidden
                            ${isDragging ? "border-cyan-400/70 bg-cyan-500/[0.06]" : "border-white/10 bg-white/[0.02] hover:border-cyan-500/40 hover:bg-cyan-500/[0.03]"}`}
                        >
                          <motion.div animate={{ opacity: isDragging ? 1 : 0 }}
                            className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(0,212,255,0.07),transparent_70%)] pointer-events-none" />

                          <div className={`relative mb-6 transition-transform duration-300 ${isDragging ? "scale-110" : "group-hover:scale-105"}`}>
                            <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-cyan-500/15 to-violet-600/10
                              border border-cyan-500/25 flex items-center justify-center
                              shadow-[0_0_30px_rgba(0,212,255,0.12)] relative">
                              <div className="absolute inset-[-8px] rounded-[22px] border border-cyan-500/15 border-dashed"
                                style={{ animation: "ring-spin-slow 8s linear infinite" }} />
                              <UploadCloud className={`w-9 h-9 transition-colors ${isDragging ? "text-cyan-300" : "text-cyan-500"}`} />
                            </div>
                            {[FileImage, FileAudio, FileVideo].map((Icon, i) => (
                              <div key={i} className="absolute w-7 h-7 rounded-xl bg-black/70 border border-white/[0.10]
                                flex items-center justify-center"
                                style={{
                                  top: i === 0 ? "-10px" : "auto",
                                  bottom: i === 2 ? "-10px" : "auto",
                                  left: i === 2 ? "-12px" : "auto",
                                  right: i === 0 ? "-12px" : i === 1 ? "-14px" : "auto",
                                }}>
                                <Icon className="w-3.5 h-3.5 text-slate-400" />
                              </div>
                            ))}
                          </div>

                          <p className="text-white font-semibold text-base mb-1">
                            {isDragging ? "Drop to submit evidence" : "Drag & drop your file here"}
                          </p>
                          <p className="text-slate-500 text-sm mb-5">or click to browse</p>
                          <div className="flex gap-2 flex-wrap justify-center">
                            {["IMAGE", "VIDEO", "AUDIO"].map(t => (
                              <span key={t} className="px-3 py-1 bg-white/[0.04] border border-white/[0.08]
                                rounded-full text-[10px] font-mono text-slate-500 tracking-wider">
                                {t}
                              </span>
                            ))}
                          </div>
                        </div>
                        {validationError && <p className="mt-4 text-red-400 text-sm text-center font-medium">{validationError}</p>}
                      </motion.div>
                    ) : (
                      /* ── FILE PREVIEW ── */
                      <motion.div key="preview" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} className="flex flex-col gap-5">
                        <div className="w-full rounded-2xl overflow-hidden bg-black/40 border border-white/[0.07] relative" style={{ minHeight: 180 }}>
                          {previewUrl && file?.type.startsWith("image/") && (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img src={previewUrl} alt="Evidence preview" className="w-full max-h-64 object-contain" />
                          )}
                          {previewUrl && file?.type.startsWith("video/") && (
                            <video src={previewUrl} className="w-full max-h-64 object-contain" muted autoPlay loop playsInline />
                          )}
                          {!previewUrl && file && (
                            <div className="flex flex-col items-center justify-center h-48 gap-4">
                              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-cyan-500/15 to-violet-600/10
                                border border-cyan-500/20 flex items-center justify-center shadow-[0_0_20px_rgba(0,212,255,0.15)]">
                                {file.type.startsWith("audio/")
                                  ? <FileAudio className="w-8 h-8 text-cyan-400" />
                                  : <File className="w-8 h-8 text-slate-400" />}
                              </div>
                              {file.type.startsWith("audio/") && (
                                <div className="flex items-end gap-1 h-8">
                                  {[3,7,5,9,6,4,8,5,7,3].map((h, i) => (
                                    <motion.div key={i} className="w-1.5 bg-cyan-500/60 rounded-full"
                                      animate={{ height: [`${h*3}px`, `${h*3+10}px`, `${h*3}px`] }}
                                      transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.09, ease: "easeInOut" }} />
                                  ))}
                                </div>
                              )}
                            </div>
                          )}
                          <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/80 to-transparent px-4 py-3">
                            <p className="text-xs font-mono text-slate-300 truncate">{file.name}</p>
                            <p className="text-[10px] text-slate-500 mt-0.5">{(file.size/1024/1024).toFixed(2)} MB · {file.type}</p>
                          </div>
                        </div>

                        <div className="flex gap-3">
                          <button onClick={handleClearFile}
                            className="flex-1 flex items-center justify-center gap-2 px-5 py-3.5 rounded-xl
                              bg-white/[0.04] border border-white/[0.10] text-slate-300 font-semibold text-sm
                              hover:bg-white/[0.08] hover:text-white transition-all">
                            <RotateCcw className="w-4 h-4" /> New Upload
                          </button>
                          <button onClick={handleInitiate}
                            className="flex-1 flex items-center justify-center gap-2 px-5 py-3.5 rounded-xl
                              bg-gradient-to-r from-emerald-500 to-cyan-500 text-white font-bold text-sm
                              hover:from-emerald-400 hover:to-cyan-400 hover:scale-[1.02]
                              hover:shadow-[0_0_30px_rgba(16,185,129,0.4)] transition-all
                              border border-white/[0.15]">
                            Initiate Analysis <ArrowRight className="w-4 h-4" />
                          </button>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </motion.div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
