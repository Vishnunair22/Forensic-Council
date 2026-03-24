"use client";

import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import {
  ChevronRight, ShieldCheck, File, UploadCloud,
  FileImage, FileAudio, FileVideo, X, ArrowRight, RotateCcw,
  PlayCircle,
} from "lucide-react";
import { useEffect, useState, useCallback, useRef, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { AGENTS_DATA, ALLOWED_MIME_TYPES } from "@/lib/constants";
import { AgentIcon } from "@/components/ui/AgentIcon";
import { GlobalFooter } from "@/components/ui/GlobalFooter";
import { useSound } from "@/hooks/useSound";
import { startInvestigation, type InvestigationResponse } from "@/lib/api";

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
    <div className="absolute inset-0 flex items-center justify-center pointer-events-none overflow-hidden sm:overflow-visible" aria-hidden="true">
      <div className="relative flex items-center justify-center w-full h-full" style={{ transform: "scale(min(1, calc(100vw / 640)))", transformOrigin: "center" }}>

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

        {/* Core specimen — forensic evidence file being scanned */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-10">
          {/* Outer selection pulse ring */}
          <motion.div
            className="absolute -inset-10 rounded-full border border-cyan-400/28"
            animate={reduced ? {} : { scale: [1, 1.10, 1], opacity: [0.28, 0.55, 0.28] }}
            transition={{ duration: 2.8, repeat: Infinity, ease: "easeInOut" }}
          />
          {/* Inner rectangular lock frame around document */}
          <motion.div
            className="absolute -inset-4 rounded border border-cyan-400/60"
            animate={reduced ? {} : { opacity: [0.45, 1, 0.45] }}
            transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut" }}
          />
          {/* Corner lock ticks */}
          {[
            "absolute -top-[7px] -left-[7px] border-t-2 border-l-2 w-3 h-3 border-cyan-400/80",
            "absolute -top-[7px] -right-[7px] border-t-2 border-r-2 w-3 h-3 border-cyan-400/80",
            "absolute -bottom-[7px] -left-[7px] border-b-2 border-l-2 w-3 h-3 border-cyan-400/80",
            "absolute -bottom-[7px] -right-[7px] border-b-2 border-r-2 w-3 h-3 border-cyan-400/80",
          ].map((cls, i) => <div key={i} className={cls} />)}
          {/* Evidence file icon */}
          <div
            className="relative flex items-center justify-center"
            style={{ animation: reduced ? "none" : "scan-glow 2s ease-in-out infinite" }}
          >
            <svg viewBox="0 0 20 26" fill="none" className="w-9 h-[46px]" xmlns="http://www.w3.org/2000/svg">
              <rect x="1.5" y="1.5" width="14" height="22" rx="2" fill="rgba(0,212,255,0.08)" stroke="rgba(0,212,255,0.88)" strokeWidth="1.4"/>
              <path d="M11 1.5 L15.5 6.5 L11 6.5 Z" fill="rgba(0,212,255,0.20)" stroke="rgba(0,212,255,0.70)" strokeWidth="1" strokeLinejoin="round"/>
              <line x1="4" y1="10" x2="12" y2="10" stroke="rgba(0,212,255,0.55)" strokeWidth="1.1" strokeLinecap="round"/>
              <line x1="4" y1="13.5" x2="13" y2="13.5" stroke="rgba(0,212,255,0.40)" strokeWidth="1.1" strokeLinecap="round"/>
              <line x1="4" y1="17" x2="10" y2="17" stroke="rgba(0,212,255,0.28)" strokeWidth="1.1" strokeLinecap="round"/>
            </svg>
          </div>
          {/* ANALYZING readout */}
          <motion.div
            className="absolute -bottom-8 left-1/2 -translate-x-1/2 whitespace-nowrap font-mono text-[11px] text-cyan-300 tracking-[0.2em] font-bold"
            animate={reduced ? {} : { opacity: [0.6, 1, 0.6] }}
            transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
          >
            ANALYZING…
          </motion.div>
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
            className={`absolute ${tag.x} ${tag.y} font-mono text-[11px] text-cyan-200
              bg-black/90 border border-cyan-500/40 px-2.5 py-1 rounded-lg backdrop-blur-sm
              shadow-[0_0_14px_rgba(0,212,255,0.18)]`}
          >
            <span className="text-cyan-400 mr-1.5">{tag.label}</span>{tag.val}
          </motion.div>
        ))}

        {/* Data readout tags — violet set (delayed) */}
        {TAGS_B.map((tag, i) => (
          <motion.div
            key={`b${i}`}
            initial={{ opacity: 0 }}
            animate={reduced ? {} : { opacity: [0, 0, 0.72, 0.72, 0] }}
            transition={{ delay: tag.delay, duration: 4.8, repeat: Infinity, repeatDelay: 3.8 }}
            className={`absolute ${tag.x} ${tag.y} font-mono text-[11px] text-violet-200
              bg-black/90 border border-violet-500/40 px-2.5 py-1 rounded-lg backdrop-blur-sm
              shadow-[0_0_12px_rgba(124,58,237,0.15)]`}
          >
            <span className="text-violet-400 mr-1.5">{tag.label}</span>{tag.val}
          </motion.div>
        ))}
      </div>
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
interface GlassCardProps {
  children: ReactNode;
  className?: string;
  glowColor?: "cyan" | "violet" | "emerald";
}

function GlassCard({
  children,
  className = "",
  glowColor = "cyan",
}: GlassCardProps) {
  const glowMap = {
    cyan:    "hover:border-cyan-400/35 hover:shadow-[0_0_60px_rgba(0,212,255,0.12),0_8px_32px_rgba(0,0,0,0.45),inset_0_1px_0_rgba(0,212,255,0.10)]",
    violet:  "hover:border-violet-400/45 hover:shadow-[0_0_70px_rgba(124,58,237,0.20),0_8px_32px_rgba(0,0,0,0.50),inset_0_1px_0_rgba(168,85,247,0.14)]",
    emerald: "hover:border-emerald-400/35 hover:shadow-[0_0_60px_rgba(16,185,129,0.12),0_8px_32px_rgba(0,0,0,0.45)]",
  }[glowColor];

  return (
    <div
      className={`glass-panel rounded-3xl transition-all duration-400 ease-out card-hover
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

    // Generate IDs now so they're consistent between landing and evidence pages.
    const caseId = "CASE-" + Date.now();
    const storedId = sessionStorage.getItem("forensic_investigator_id");
    const validIdPattern = /^REQ-\d{5,10}$/;
    const investigatorId =
      storedId && validIdPattern.test(storedId)
        ? storedId
        : "REQ-" + (Math.floor(Math.random() * 900000) + 100000);

    sessionStorage.setItem("forensic_pending_file_name", file.name);
    sessionStorage.setItem("forensic_case_id", caseId);
    sessionStorage.setItem("forensic_investigator_id", investigatorId);
    sessionStorage.setItem("forensic_auto_start", "true");
    (window as { __forensic_pending_file?: File }).__forensic_pending_file = file;

    // Fire the upload immediately while the 380 ms animation plays.
    // The evidence page will await this already-in-flight Promise instead of
    // starting a second startInvestigation call from scratch.
    (
      window as {
        __forensic_investigation_promise?: Promise<InvestigationResponse>;
      }
    ).__forensic_investigation_promise = startInvestigation(
      file,
      caseId,
      investigatorId
    );

    setTimeout(() => router.push("/evidence"), 200);
  };

  useEffect(() => {
    return () => { if (previewUrl) URL.revokeObjectURL(previewUrl); };
  }, [previewUrl]);

  // Close modal on Escape key
  useEffect(() => {
    if (!modalOpen) return;
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === "Escape") handleModalClose(); };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modalOpen]);

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

      {/* Skip-to-content link for keyboard users */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[9999]
          focus:px-4 focus:py-2 focus:bg-cyan-500 focus:text-black focus:rounded-lg focus:font-semibold focus:text-sm"
      >
        Skip to main content
      </a>

      {/* ── Header ── */}
      <header className="fixed top-0 w-full px-6 py-4 flex items-center justify-between
        border-b border-white/[0.08] bg-[#030308]/85 backdrop-blur-2xl z-50 shadow-[0_4px_30px_rgba(0,0,0,0.5)]"
        role="banner"
      >
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-gradient-to-br from-cyan-400 to-violet-600 rounded-lg flex items-center justify-center
            font-bold text-[#030308] text-sm shadow-[0_0_20px_rgba(0,212,255,0.3)]"
            style={{ fontFamily: "var(--font-sans)" }}>FC</div>
          <span className="text-lg font-bold tracking-tight bg-gradient-to-r from-white to-slate-400 bg-clip-text text-transparent">
            Forensic Council
          </span>
        </div>
        <div className="flex items-center gap-8">
          <nav className="hidden md:flex items-center gap-6">
            <a href="#process-title" className="text-[12px] font-mono text-slate-300 hover:text-cyan-300 transition-colors uppercase tracking-widest font-semibold">Process</a>
            <a href="#council-title" className="text-[12px] font-mono text-slate-300 hover:text-cyan-300 transition-colors uppercase tracking-widest font-semibold">The Council</a>
          </nav>
          <span className="text-[11px] font-mono text-slate-400 hidden sm:block border-l border-white/20 pl-6 font-bold uppercase tracking-wider">ACADEMIC RESEARCH PROJECT</span>
        </div>
      </header>

      {/* ══════════════════════════════════════════════════════════
          MAIN CONTENT
      ══════════════════════════════════════════════════════════ */}
      <main id="main-content">

      {/* HERO */}
      <section
        aria-labelledby="hero-title"
        className="relative w-full min-h-screen flex flex-col items-center justify-center px-6 pt-20 z-10 overflow-hidden"
      >
        <MicroscopeScanner />

        <div className="relative z-30 flex flex-col items-center text-center max-w-4xl mx-auto">

          {/* Headline */}
          <motion.h1
            id="hero-title"
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
            className="text-slate-300 text-lg sm:text-xl max-w-2xl mb-12 leading-relaxed font-normal"
          >
            Five specialist AI agents independently examine your evidence — pixel integrity, audio authenticity,
            object detection, temporal analysis, and metadata provenance — then the Council Arbiter synthesises
            a cryptographically-signed forensic verdict.
          </motion.p>

          {/* CTA */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-6 relative z-10 w-full max-w-2xl px-4">
            <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.45 }} className="w-full sm:w-auto">
              <EnvelopeCTA onOpen={handleCTAClick} phase={envPhase} />
            </motion.div>
            
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════════
          HOW IT WORKS
      ══════════════════════════════════════════════════════════ */}
      <section aria-labelledby="process-title" className="relative z-10 py-32 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-20">
            <p className="text-xs font-mono text-cyan-400 uppercase tracking-[0.25em] mb-3 font-bold">Process</p>
            <h2 id="process-title" className="text-4xl md:text-5xl font-bold text-white">How Forensic Council Works</h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 relative">
            {/* Connector line */}
            <div className="hidden md:block absolute top-[108px] left-[12%] right-[12%] h-px
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
                className="relative mt-9 group"
              >
                {/* Step bubble — sibling of GlassCard so glass-panel overflow:hidden doesn't clip it */}
                <div className="absolute -top-[34px] left-1/2 -translate-x-1/2 w-[68px] h-[68px] rounded-full
                  bg-gradient-to-b from-[#0a0a18] to-[#050510]
                  border border-cyan-500/40 flex items-center justify-center z-10
                  font-mono text-xl text-cyan-300 font-bold
                  shadow-[0_0_28px_rgba(0,212,255,0.22),inset_0_1px_0_rgba(0,212,255,0.15)]
                  group-hover:border-cyan-400/65 group-hover:shadow-[0_0_40px_rgba(0,212,255,0.38),inset_0_1px_0_rgba(0,212,255,0.22)]
                  transition-all duration-300"
                  aria-hidden="true">
                  {item.step}
                </div>
                <GlassCard className="p-8 pt-12 flex flex-col items-center text-center">
                  <h3 className="text-base font-bold text-white mb-3 text-center tracking-wide">{item.title}</h3>
                  <p className="text-slate-200 text-sm leading-relaxed text-center font-medium">{item.desc}</p>
                </GlassCard>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════════
          MEET THE COUNCIL
      ══════════════════════════════════════════════════════════ */}
      <section aria-labelledby="council-title" className="relative z-10 pb-32 pt-8 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <p className="text-xs font-mono text-violet-300 uppercase tracking-[0.25em] mb-3 font-bold">Council Members</p>
            <h2 id="council-title" className="text-4xl md:text-5xl font-bold mb-5
              bg-gradient-to-r from-cyan-300 to-violet-300 bg-clip-text text-transparent inline-block">
              Meet the Council
            </h2>
            <p className="text-slate-200 text-lg max-w-2xl mx-auto leading-relaxed text-justify-section font-medium">
              Five specialist agents analyse evidence independently, then the Council Arbiter synthesises
              their findings into a unified verdict with confidence scoring.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 auto-rows-[minmax(180px,auto)]">
            {/* Agent 1 - Wide span */}
            <motion.div
              className="lg:col-span-2 lg:row-span-1"
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ delay: 0.1, duration: 0.7 }}
              whileHover={{ y: -5, scale: 1.01 }}
            >
              <GlassCard className="p-7 flex flex-col md:flex-row items-center gap-6 h-full group">
                <div className="p-4 bg-gradient-to-br from-cyan-500/15 to-cyan-600/5 text-cyan-400 rounded-2xl
                  shadow-[inset_0_0_18px_rgba(0,212,255,0.08),0_0_16px_rgba(0,212,255,0.10)] border border-cyan-500/22
                  relative z-10 group-hover:scale-110 transition-transform">
                  <AgentIcon role={AGENTS_DATA[0].role} />
                </div>
                <div className="flex-1 text-center md:text-left">
                  <h3 className="text-lg font-bold text-white mb-1 tracking-wide">{AGENTS_DATA[0].name}</h3>
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-950/70 text-cyan-300 border border-cyan-500/22 uppercase tracking-widest font-semibold mb-3 inline-block">
                    {AGENTS_DATA[0].role}
                  </span>
                  <p className="text-sm text-slate-400 leading-relaxed mb-4">{AGENTS_DATA[0].desc}</p>
                </div>
              </GlassCard>
            </motion.div>

            {/* Agent 2 - Standard */}
            <motion.div
              className="lg:col-span-1 lg:row-span-1"
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ delay: 0.2, duration: 0.7 }}
              whileHover={{ y: -5, scale: 1.01 }}
            >
              <GlassCard className="p-6 flex flex-col items-center text-center h-full group">
                <div className="p-3 bg-gradient-to-br from-cyan-500/15 to-cyan-600/5 text-cyan-400 rounded-xl mb-4
                  shadow-[inset_0_0_18px_rgba(0,212,255,0.08)] border border-cyan-500/22 group-hover:scale-110 transition-transform">
                  <AgentIcon role={AGENTS_DATA[1].role} />
                </div>
                <h3 className="text-base font-bold text-white mb-1 tracking-wide">{AGENTS_DATA[1].name}</h3>
                <p className="text-xs text-slate-400 leading-relaxed line-clamp-3">{AGENTS_DATA[1].desc}</p>
              </GlassCard>
            </motion.div>

            {/* Agent 3 - Standard */}
            <motion.div
              className="lg:col-span-1 lg:row-span-1"
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ delay: 0.3, duration: 0.7 }}
              whileHover={{ y: -5, scale: 1.01 }}
            >
              <GlassCard className="p-6 flex flex-col items-center text-center h-full group">
                <div className="p-3 bg-gradient-to-br from-cyan-500/15 to-cyan-600/5 text-cyan-400 rounded-xl mb-4
                  shadow-[inset_0_0_18px_rgba(0,212,255,0.08)] border border-cyan-500/22 group-hover:scale-110 transition-transform">
                  <AgentIcon role={AGENTS_DATA[2].role} />
                </div>
                <h3 className="text-base font-bold text-white mb-1 tracking-wide">{AGENTS_DATA[2].name}</h3>
                <p className="text-xs text-slate-400 leading-relaxed line-clamp-3">{AGENTS_DATA[2].desc}</p>
              </GlassCard>
            </motion.div>

            {/* Council Arbiter - Large Featured span */}
            <motion.div
              className="lg:col-span-2 lg:row-span-1"
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ delay: 0.4, duration: 0.7 }}
              whileHover={{ y: -5, scale: 1.015 }}
            >
              <GlassCard
                glowColor="violet"
                className="p-8 flex flex-col md:flex-row items-center gap-8 h-full group
                  border-violet-500/28 bg-gradient-to-br from-violet-500/[0.08] to-violet-900/[0.03]"
              >
                <div className="absolute inset-0 rounded-3xl bg-[radial-gradient(ellipse_at_top_right,rgba(124,58,237,0.14),transparent_55%)] pointer-events-none" />
                <div className="p-6 bg-gradient-to-br from-violet-500/22 to-violet-600/10 text-violet-300 rounded-2xl
                  shadow-[inset_0_0_20px_rgba(124,58,237,0.12),0_0_18px_rgba(124,58,237,0.14)] border border-violet-500/32
                  relative z-10 group-hover:scale-110 transition-transform">
                  <ShieldCheck className="w-10 h-10" aria-hidden="true" />
                </div>
                <div className="flex-1 text-center md:text-left relative z-10">
                  <h3 className="text-xl font-bold text-white mb-1 tracking-wide drop-shadow-[0_0_14px_rgba(124,58,237,0.5)]">Council Arbiter</h3>
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-violet-900/70 text-violet-200 border border-violet-500/32 uppercase tracking-widest font-bold mb-3 inline-block">
                    Executive Synthesis
                  </span>
                  <p className="text-sm text-slate-400 leading-relaxed">
                    Cross-references findings, resolves contradictions, and produces the final forensic verdict.
                  </p>
                </div>
              </GlassCard>
            </motion.div>

            {/* Agent 4 - Standard */}
            <motion.div
              className="lg:col-span-1 lg:row-span-1"
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ delay: 0.5, duration: 0.7 }}
              whileHover={{ y: -5, scale: 1.01 }}
            >
              <GlassCard className="p-6 flex flex-col items-center text-center h-full group">
                <div className="p-3 bg-gradient-to-br from-cyan-500/15 to-cyan-600/5 text-cyan-400 rounded-xl mb-4
                  shadow-[inset_0_0_18px_rgba(0,212,255,0.08)] border border-cyan-500/22 group-hover:scale-110 transition-transform">
                  <AgentIcon role={AGENTS_DATA[3].role} />
                </div>
                <h3 className="text-base font-bold text-white mb-1 tracking-wide">{AGENTS_DATA[3].name}</h3>
                <p className="text-xs text-slate-400 leading-relaxed line-clamp-3">{AGENTS_DATA[3].desc}</p>
              </GlassCard>
            </motion.div>

            {/* Agent 5 - Standard */}
            <motion.div
              className="lg:col-span-1 lg:row-span-1"
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ delay: 0.6, duration: 0.7 }}
              whileHover={{ y: -5, scale: 1.01 }}
            >
              <GlassCard className="p-6 flex flex-col items-center text-center h-full group">
                <div className="p-3 bg-gradient-to-br from-cyan-500/15 to-cyan-600/5 text-cyan-400 rounded-xl mb-4
                  shadow-[inset_0_0_18px_rgba(0,212,255,0.08)] border border-cyan-500/22 group-hover:scale-110 transition-transform">
                  <AgentIcon role={AGENTS_DATA[4].role} />
                </div>
                <h3 className="text-base font-bold text-white mb-1 tracking-wide">{AGENTS_DATA[4].name}</h3>
                <p className="text-xs text-slate-400 leading-relaxed line-clamp-3">{AGENTS_DATA[4].desc}</p>
              </GlassCard>
            </motion.div>
          </div>
        </div>
      </section>

      </main>{/* end #main-content */}

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
              initial={{ scale: 0.90, opacity: 0, y: 28 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.93, opacity: 0, y: 16 }}
              transition={{ type: "spring", stiffness: 320, damping: 30 }}
              role="dialog"
              aria-modal="true"
              aria-labelledby="evidence-modal-title"
              className="relative w-full max-w-lg z-10 glass-modal rounded-[1.75rem]"
            >
              {/* Ambient cyan glow behind modal */}
              <div className="absolute -inset-4 rounded-[2.25rem] bg-cyan-500/[0.04] blur-2xl pointer-events-none -z-10" />

              {/* Envelope opening reveal — content slides up from "inside" */}
              <motion.div
                initial={{ y: 24, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ delay: 0.10, duration: 0.42, ease: [0.22, 1, 0.36, 1] }}
              >
                {/* Modal header */}
                <div className="px-7 pt-7 pb-5 flex items-start justify-between border-b border-white/[0.07]">
                  <div>
                    <div className="flex items-center gap-3 mb-1">
                      <div className="w-9 h-9 rounded-xl
                        bg-gradient-to-br from-cyan-500/25 to-cyan-600/10
                        border border-cyan-500/35 flex items-center justify-center
                        shadow-[0_0_14px_rgba(0,212,255,0.18)]">
                        <UploadCloud className="w-4.5 h-4.5 text-cyan-300" aria-hidden="true" />
                      </div>
                      <div>
                        <h2 id="evidence-modal-title" className="text-lg font-bold text-white tracking-tight">Evidence Intake</h2>
                        <p className="text-slate-500 text-xs mt-0.5">Submit a digital artifact for council analysis</p>
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={handleModalClose}
                    // eslint-disable-next-line jsx-a11y/no-autofocus
                    autoFocus
                    aria-label="Close evidence intake modal"
                    className="p-2 text-slate-500 hover:text-white hover:bg-white/[0.08] rounded-xl transition-all duration-200 border border-transparent hover:border-white/[0.10]"
                  >
                    <X className="w-4.5 h-4.5" aria-hidden="true" />
                  </button>
                </div>

                {/* Modal body */}
                <div className="px-7 pb-7 pt-5">
                  <AnimatePresence mode="wait">
                    {!file ? (
                      /* ── DROP ZONE ── */
                      <motion.div key="dz" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}>
                        <input
                          type="file"
                          ref={fileInputRef}
                          className="sr-only"
                          accept="image/*,video/*,audio/*"
                          aria-label="Upload evidence file"
                          onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
                        />
                        <div
                          role="button"
                          tabIndex={0}
                          aria-label="File drop zone — click or press Enter to browse files"
                          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                          onDragLeave={() => setIsDragging(false)}
                          onDrop={(e) => { e.preventDefault(); setIsDragging(false); e.dataTransfer.files?.[0] && handleFile(e.dataTransfer.files[0]); }}
                          onClick={() => fileInputRef.current?.click()}
                          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInputRef.current?.click(); } }}
                          className={`relative cursor-pointer rounded-2xl border-2 border-dashed
                            flex flex-col items-center justify-center py-12 px-8 text-center
                            transition-all duration-300 group overflow-hidden
                            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 focus-visible:ring-offset-2 focus-visible:ring-offset-transparent
                            ${isDragging
                              ? "border-cyan-400/75 bg-cyan-500/[0.07] shadow-[inset_0_0_40px_rgba(0,212,255,0.05)]"
                              : "border-white/[0.09] bg-white/[0.018] hover:border-cyan-500/45 hover:bg-cyan-500/[0.035] hover:shadow-[inset_0_0_30px_rgba(0,212,255,0.04)]"}`}
                        >
                          {/* Drag radial glow */}
                          <motion.div animate={{ opacity: isDragging ? 1 : 0 }} transition={{ duration: 0.2 }}
                            className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(0,212,255,0.08),transparent_68%)] pointer-events-none" />

                          <div className={`relative mb-5 transition-transform duration-300 ${isDragging ? "scale-112" : "group-hover:scale-108"}`}>
                            <div className="w-[72px] h-[72px] rounded-2xl
                              bg-gradient-to-br from-cyan-500/18 to-violet-600/12
                              border border-cyan-500/28 flex items-center justify-center
                              shadow-[0_0_28px_rgba(0,212,255,0.14),inset_0_1px_0_rgba(255,255,255,0.08)] relative">
                              <div className="absolute inset-[-7px] rounded-[22px] border border-cyan-500/18 border-dashed"
                                style={{ animation: "ring-spin-slow 8s linear infinite" }} />
                              <UploadCloud className={`w-8 h-8 transition-colors duration-200 ${isDragging ? "text-cyan-200" : "text-cyan-400"}`} aria-hidden="true" />
                            </div>
                            {[FileImage, FileAudio, FileVideo].map((Icon, idx) => (
                              <div key={idx}
                                className="absolute w-6 h-6 rounded-lg bg-[#0a0a18]/90 border border-white/[0.12]
                                  flex items-center justify-center shadow-sm"
                                style={{
                                  top: idx === 0 ? "-8px" : "auto",
                                  bottom: idx === 2 ? "-8px" : "auto",
                                  left: idx === 2 ? "-10px" : "auto",
                                  right: idx === 0 ? "-10px" : idx === 1 ? "-12px" : "auto",
                                }}>
                                <Icon className="w-3 h-3 text-slate-400" aria-hidden="true" />
                              </div>
                            ))}
                          </div>

                          <p className="text-white font-semibold text-sm mb-1 tracking-wide">
                            {isDragging ? "Drop to submit evidence" : "Drag & drop your file here"}
                          </p>
                          <p className="text-slate-500 text-xs mb-4">or click to browse</p>
                          <div className="flex gap-2 flex-wrap justify-center">
                            {["IMAGE", "VIDEO", "AUDIO"].map(t => (
                              <span key={t} className="px-2.5 py-0.5 bg-white/[0.04] border border-white/[0.08]
                                rounded-full text-[10px] font-mono text-slate-500 tracking-widest">
                                {t}
                              </span>
                            ))}
                          </div>
                        </div>
                        {validationError && (
                          <motion.p
                            role="alert"
                            initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }}
                            className="mt-3 text-red-400 text-xs text-center font-medium flex items-center justify-center gap-1.5"
                          >
                            <span className="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0" aria-hidden="true" />
                            {validationError}
                          </motion.p>
                        )}
                      </motion.div>
                    ) : (
                      /* ── FILE PREVIEW / SUCCESS ── */
                      <motion.div key="preview" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} className="flex flex-col gap-4">
                        {/* Preview card */}
                        <div className="w-full rounded-2xl overflow-hidden
                          bg-gradient-to-b from-white/[0.03] to-black/30
                          border border-white/[0.08] relative shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]"
                          style={{ minHeight: 168 }}>
                          {previewUrl && file?.type.startsWith("image/") && (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img src={previewUrl} alt="Evidence preview" className="w-full max-h-60 object-contain" />
                          )}
                          {previewUrl && file?.type.startsWith("video/") && (
                            <video src={previewUrl} className="w-full max-h-60 object-contain" muted autoPlay loop playsInline />
                          )}
                          {!previewUrl && file && (
                            <div className="flex flex-col items-center justify-center h-44 gap-3">
                              <div className="w-14 h-14 rounded-2xl
                                bg-gradient-to-br from-cyan-500/18 to-violet-600/10
                                border border-cyan-500/22 flex items-center justify-center
                                shadow-[0_0_20px_rgba(0,212,255,0.18)]">
                                {file.type.startsWith("audio/")
                                  ? <FileAudio className="w-7 h-7 text-cyan-400" aria-hidden="true" />
                                  : <File className="w-7 h-7 text-slate-400" aria-hidden="true" />}
                              </div>
                              {file.type.startsWith("audio/") && (
                                <div className="flex items-end gap-1 h-7">
                                  {[3,7,5,9,6,4,8,5,7,3].map((h, i) => (
                                    <motion.div key={i} className="w-1.5 bg-gradient-to-t from-cyan-600 to-cyan-400 rounded-full"
                                      animate={{ height: [`${h*3}px`, `${h*3+10}px`, `${h*3}px`] }}
                                      transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.09, ease: "easeInOut" }} />
                                  ))}
                                </div>
                              )}
                            </div>
                          )}
                          {/* File info overlay */}
                          <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/90 via-black/60 to-transparent px-4 py-3">
                            <div className="flex items-center gap-2">
                              <div className="w-5 h-5 rounded-md bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center shrink-0">
                                <span className="text-emerald-400 text-[9px] font-bold">✓</span>
                              </div>
                              <div className="min-w-0">
                                <p className="text-xs font-semibold text-slate-200 truncate">{file.name}</p>
                                <p className="text-[10px] text-slate-500 mt-0.5">{(file.size/1024/1024).toFixed(2)} MB · {file.type.split("/")[1]?.toUpperCase() || file.type}</p>
                              </div>
                            </div>
                          </div>
                        </div>

                        {/* Action buttons */}
                        <div className="flex gap-2.5">
                          <button
                            onClick={handleClearFile}
                            className="btn btn-ghost flex-1 py-3 rounded-xl text-sm"
                          >
                            <RotateCcw className="w-3.5 h-3.5" aria-hidden="true" /> New Upload
                          </button>
                          <button
                            onClick={handleInitiate}
                            className="btn btn-primary flex-1 py-3 rounded-xl text-sm font-bold"
                          >
                            Initiate Analysis <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
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
