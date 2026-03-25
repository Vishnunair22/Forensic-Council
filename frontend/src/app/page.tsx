"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  ShieldCheck, File, UploadCloud,
  X, ArrowRight,
  Scale, Fingerprint, Scan, Globe
} from "lucide-react";
import { useEffect, useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { AGENTS_DATA, ALLOWED_MIME_TYPES } from "@/lib/constants";
import { AgentIcon } from "@/components/ui/AgentIcon";
import { GlobalFooter } from "@/components/ui/GlobalFooter";
import { useSound } from "@/hooks/useSound";
import { startInvestigation } from "@/lib/api";

/* ─── Precomputed particle data ───────────────────────────────────── */
const PARTICLE_DATA = [...Array(18)].map(() => ({
  x: (Math.random() - 0.5) * 1400,
  y: (Math.random() - 0.5) * 900,
  duration: Math.random() * 12 + 10,
  delay: Math.random() * 6,
  showLine: Math.random() > 0.45,
  isCyan: Math.random() > 0.5,
}));

/* ─── Microscope Scanner Animation ───────────────────────────────── */
function MicroscopeScanner() {
  return (
    <div
      className="absolute inset-0 flex items-center justify-center pointer-events-none z-0 overflow-hidden"
      aria-hidden="true"
    >
      {/* Ambient glow orbs — subtle, not dominant */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] rounded-full blur-[160px] animate-pulse"
        style={{ background: "rgba(34,211,238,0.028)" }} />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full blur-[130px]"
        style={{ background: "rgba(129,140,248,0.022)" }} />

      <div className="relative w-full max-w-5xl h-[700px] flex items-center justify-center">

        {/* Evidence Document */}
        <motion.div
          initial={{ opacity: 0, scale: 0.88, y: 30 }}
          animate={{ opacity: 0.55, scale: 1, y: 0 }}
          transition={{ duration: 1.8, ease: "easeOut" }}
          className="relative w-72 h-[440px] rounded-2xl overflow-hidden"
          style={{
            background: "rgba(255,255,255,0.025)",
            backdropFilter: "blur(16px)",
            border: "1px solid rgba(255,255,255,0.07)",
            boxShadow: "0 0 60px rgba(34,211,238,0.06), 0 40px 80px rgba(0,0,0,0.5)"
          }}
        >
          {/* Dot grid inside doc */}
          <div
            className="absolute inset-0 opacity-[0.04]"
            style={{
              backgroundImage: "radial-gradient(circle, white 1px, transparent 1px)",
              backgroundSize: "14px 14px"
            }}
          />

          {/* Content mockup lines */}
          <div className="p-8 space-y-5">
            <div className="h-1.5 w-2/5 rounded-full bg-cyan-400/20" />
            <div className="space-y-3 pt-1">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="h-[1px] rounded-full bg-white/[0.04] w-full" />
              ))}
            </div>
            {/* Image placeholder with fingerprint */}
            <div className="relative h-28 w-full rounded-xl overflow-hidden border border-white/[0.04]"
              style={{ background: "rgba(34,211,238,0.04)" }}
            >
              <div className="absolute inset-0 flex items-center justify-center">
                <Fingerprint className="w-16 h-16 text-cyan-400/10" strokeWidth={0.5} />
              </div>
              {/* shimmer sweep */}
              <motion.div
                animate={{ left: ["-100%", "200%"] }}
                transition={{ duration: 2.8, repeat: Infinity, ease: "linear", repeatDelay: 1 }}
                className="absolute top-0 bottom-0 w-16 skew-x-12"
                style={{ background: "linear-gradient(to right, transparent, rgba(34,211,238,0.12), transparent)" }}
              />
            </div>
            <div className="space-y-3">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="h-[1px] rounded-full bg-white/[0.04] w-full" />
              ))}
            </div>
          </div>

          {/* Precision scanning beam */}
          <motion.div
            animate={{ top: ["-3%", "103%", "-3%"] }}
            transition={{ duration: 5.5, repeat: Infinity, ease: "easeInOut" }}
            className="absolute left-0 right-0 z-10"
            style={{ height: "1px", background: "#22D3EE", boxShadow: "0 0 18px rgba(34,211,238,0.9), 0 0 40px rgba(34,211,238,0.4)" }}
          >
            <div className="absolute right-0 top-0 h-[1px] w-20 opacity-60"
              style={{ background: "linear-gradient(to left, #22D3EE, transparent)" }} />
            <div className="absolute left-0 top-0 h-[1px] w-20 opacity-60"
              style={{ background: "linear-gradient(to right, #22D3EE, transparent)" }} />
          </motion.div>

          {/* Tech readout */}
          <div className="absolute bottom-4 left-5 right-5 flex justify-between items-end text-[7px] font-mono text-cyan-400/30 uppercase tracking-[0.18em]">
            <span>ID: FC-{"\u200B"}8821<br />AUTH: VERIFIED</span>
            <span className="text-right">LAYER: MICRO<br />SENS: ULTRA</span>
          </div>
        </motion.div>

        {/* Scanning lens / mechanical circle */}
        <motion.div
          animate={{
            x: [-160, 160, -160],
            y: [-90, 90, -90],
            rotate: [0, 360],
          }}
          transition={{
            x: { duration: 22, repeat: Infinity, ease: "easeInOut" },
            y: { duration: 16, repeat: Infinity, ease: "easeInOut" },
            rotate: { duration: 65, repeat: Infinity, ease: "linear" },
          }}
          className="absolute z-20 w-60 h-60 rounded-full flex items-center justify-center overflow-hidden"
          style={{
            background: "rgba(34,211,238,0.04)",
            backdropFilter: "blur(10px)",
            border: "1px solid rgba(34,211,238,0.18)",
            boxShadow: "0 0 80px rgba(34,211,238,0.08), inset 0 0 30px rgba(34,211,238,0.04)"
          }}
        >
          {/* Concentric rings */}
          <div className="absolute inset-0 rounded-full border border-white/[0.04]"
            style={{ animation: "spin-slow 45s linear infinite" }} />
          <div className="absolute inset-[12%] rounded-full border border-violet-400/[0.08]"
            style={{ animation: "spin-slow 28s linear infinite reverse" }} />
          <div className="absolute inset-[25%] rounded-full border border-cyan-400/[0.06]" />

          {/* Crosshair */}
          <div className="absolute inset-0 flex items-center justify-center opacity-20">
            <div className="w-full h-[1px] bg-white/10" />
          </div>
          <div className="absolute inset-0 flex items-center justify-center opacity-20">
            <div className="h-full w-[1px] bg-white/10" />
          </div>

          {/* Tick marks */}
          {[...Array(12)].map((_, i) => (
            <div
              key={i}
              className="absolute w-[1px] h-2.5"
              style={{
                background: "rgba(34,211,238,0.2)",
                transform: `rotate(${i * 30}deg) translateY(-110px)`,
              }}
            />
          ))}

          <Scan className="w-16 h-16 text-cyan-400/25" strokeWidth={0.5} />

          {/* Sweep flash */}
          <motion.div
            animate={{ opacity: [0, 0.4, 0] }}
            transition={{ duration: 2.2, repeat: Infinity }}
            className="absolute inset-0 rounded-full"
            style={{ background: "conic-gradient(from 0deg, transparent 0%, rgba(34,211,238,0.06) 30%, transparent 60%)" }}
          />
        </motion.div>

        {/* Floating data particles */}
        {PARTICLE_DATA.map((p, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0 }}
            animate={{ opacity: [0, 0.45, 0], scale: [0.4, 1.3, 0.4], x: p.x, y: p.y }}
            transition={{ duration: p.duration, repeat: Infinity, delay: p.delay }}
            className="absolute"
          >
            <div className={`w-1 h-1 rounded-full blur-[1px] ${p.isCyan ? "bg-cyan-400/40" : "bg-violet-400/30"}`} />
            {p.showLine && (
              <div className={`mt-1.5 h-[1px] w-6 ${p.isCyan ? "bg-cyan-400/15" : "bg-violet-400/10"}`} />
            )}
          </motion.div>
        ))}
      </div>
    </div>
  );
}

/* ─── CTA Button ──────────────────────────────────────────────────── */
type EnvelopePhase = "idle" | "opening" | "open" | "closing";

function ActionBtn({ onOpen, phase }: { onOpen: () => void; phase: EnvelopePhase }) {
  const busy = phase !== "idle" && phase !== "closing";
  return (
    <div className="relative inline-block group">
      <button
        onClick={onOpen}
        disabled={busy}
        className={`btn-premium-amber shadow-lg transition-all ${busy ? "opacity-50 grayscale pointer-events-none" : ""}`}
      >
        <span className="relative z-10">
          {busy ? "Initializing Systems…" : "Begin Forensic Analysis"}
        </span>
        <ArrowRight className={`w-5 h-5 relative z-10 transition-transform duration-300 ${!busy ? "group-hover:translate-x-1" : ""}`} />
      </button>
      {/* Outer glow halo */}
      <div className="absolute inset-0 -z-10 blur-2xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-500"
        style={{ background: "rgba(34,211,238,0.18)" }} />
    </div>
  );
}

/* ─── Main Landing Page ───────────────────────────────────────────── */
export default function LandingPage() {
  const { playSound } = useSound();
  const router = useRouter();
  const [modalOpen, setModalOpen] = useState(false);
  const [envPhase, setEnvPhase] = useState<EnvelopePhase>("idle");
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isMounted, setIsMounted] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setIsMounted(true);
    window.scrollTo(0, 0);
  }, []);

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

  const handleClearFile = useCallback(() => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(null); setPreviewUrl(null); setValidationError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, [previewUrl]);

  const handleCTAClick = () => {
    if (envPhase !== "idle") return;
    playSound("envelope_open");
    setEnvPhase("opening");
    setTimeout(() => { setEnvPhase("open"); setModalOpen(true); }, 500);
  };

  const handleModalClose = useCallback(() => {
    playSound("envelope_close");
    setEnvPhase("closing");
    setModalOpen(false);
    handleClearFile();
    setTimeout(() => setEnvPhase("idle"), 400);
  }, [playSound, handleClearFile]);

  const [isTransitioning, setIsTransitioning] = useState(false);

  const handleInitiate = () => {
    if (!file || isTransitioning) return;
    setIsTransitioning(true);
    playSound("envelope_close");
    setEnvPhase("closing");
    const caseId = "CASE-" + Date.now();
    const storedId = sessionStorage.getItem("forensic_investigator_id");
    const validIdPattern = /^REQ-\d{5,10}$/;
    const investigatorId = storedId && validIdPattern.test(storedId)
      ? storedId
      : "REQ-" + (Math.floor(Math.random() * 900000) + 100000);
    sessionStorage.setItem("forensic_pending_file_name", file.name);
    sessionStorage.setItem("forensic_case_id", caseId);
    sessionStorage.setItem("forensic_investigator_id", investigatorId);
    sessionStorage.setItem("forensic_auto_start", "true");
    (window as unknown as Record<string, unknown>).__forensic_pending_file = file;
    (window as unknown as Record<string, unknown>).__forensic_investigation_promise = startInvestigation(
      file, caseId, investigatorId
    );
    setTimeout(() => router.push("/evidence"), 200);
  };

  useEffect(() => {
    return () => { if (previewUrl) URL.revokeObjectURL(previewUrl); };
  }, [previewUrl]);

  useEffect(() => {
    if (!modalOpen) return;
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === "Escape") handleModalClose(); };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [modalOpen, handleModalClose]);

  if (!isMounted) return <div className="min-h-screen bg-background" />;

  return (
    <div className="relative min-h-screen bg-background text-foreground font-sans selection:bg-cyan-500/25">

      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[9999] focus:px-4 focus:py-2 focus:bg-cyan-500 focus:text-black focus:rounded-lg focus:font-bold"
      >
        Skip to main content
      </a>

      {/* ── Floating Header ── */}
      <header className="fixed top-0 left-0 right-0 z-[60] px-6 h-[68px] flex items-center justify-between"
        style={{
          background: "rgba(3,11,26,0.65)",
          backdropFilter: "blur(24px)",
          WebkitBackdropFilter: "blur(24px)",
          borderBottom: "1px solid rgba(255,255,255,0.05)"
        }}
      >
        <div
          className="flex items-center gap-4 cursor-pointer group"
          onClick={() => router.push("/")}
          role="button"
          aria-label="Forensic Council Home"
          tabIndex={0}
          onKeyDown={(e) => e.key === "Enter" && router.push("/")}
        >
          {/* Logo mark */}
          <div
            className="w-9 h-9 rounded-lg flex items-center justify-center font-black text-xs tracking-widest transition-all duration-300 group-hover:shadow-[0_0_20px_rgba(34,211,238,0.25)]"
            style={{
              background: "rgba(34,211,238,0.08)",
              border: "1px solid rgba(34,211,238,0.2)",
              color: "#22D3EE"
            }}
          >
            FC
          </div>
          <span className="text-[11px] font-black uppercase tracking-[0.45em] text-white/85 group-hover:text-cyan-400 transition-colors duration-300">
            Forensic Council
          </span>
        </div>

        {/* Nav hint */}
        <div className="hidden sm:flex items-center gap-2 text-[9px] font-mono text-white/20 uppercase tracking-[0.3em]">
          <div className="w-1.5 h-1.5 rounded-full bg-cyan-400/60 animate-pulse" />
          System Online
        </div>
      </header>

      <main id="main-content" className="relative z-10">

        {/* ════════════ HERO ════════════ */}
        <section
          aria-labelledby="hero-title"
          className="relative w-full min-h-screen flex flex-col items-center justify-center px-6 pt-24 overflow-hidden"
        >
          <MicroscopeScanner />

          <div className="relative z-30 flex flex-col items-center text-center max-w-5xl mx-auto py-16">

            {/* Badge */}
            <motion.div
              initial={{ opacity: 0, y: -16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7 }}
              className="mb-10 px-5 py-2 rounded-full inline-flex items-center gap-3"
              style={{
                background: "rgba(34,211,238,0.07)",
                border: "1px solid rgba(34,211,238,0.15)",
                boxShadow: "0 0 24px rgba(34,211,238,0.08)"
              }}
            >
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-50" />
                <span className="relative inline-flex rounded-full h-full w-full bg-cyan-400" />
              </span>
              <span className="text-[9px] font-bold uppercase tracking-[0.65em] text-cyan-400">
                Advanced Forensic Intelligence
              </span>
            </motion.div>

            {/* Headline */}
            <motion.h1
              id="hero-title"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.9, ease: "easeOut", delay: 0.1 }}
              className="text-5xl sm:text-6xl md:text-8xl font-black mb-8 tracking-tight leading-[0.9]"
            >
              Multi&#8209;Agent <br />
              <span className="text-gradient-hero">Forensic Analysis</span>
            </motion.h1>

            {/* Subtext */}
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 0.65 }}
              transition={{ delay: 0.35, duration: 0.9 }}
              className="text-slate-300 text-lg sm:text-xl max-w-2xl mb-14 font-normal leading-relaxed px-4"
            >
              Autonomous specialist agents independently audit digital evidence, resolve artifacts,
              and synthesize objective forensic verdicts with cryptographic certainty.
            </motion.p>

            {/* CTA */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.55 }}
            >
              <ActionBtn onOpen={handleCTAClick} phase={envPhase} />
            </motion.div>

            {/* Scroll hint */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 0.3 }}
              transition={{ delay: 2, duration: 1 }}
              className="absolute bottom-12 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2"
            >
              <span className="text-[8px] font-mono uppercase tracking-[0.5em] text-white/40">Explore</span>
              <motion.div
                animate={{ y: [0, 6, 0] }}
                transition={{ duration: 1.5, repeat: Infinity }}
                className="w-[1px] h-8 bg-gradient-to-b from-white/20 to-transparent"
              />
            </motion.div>
          </div>
        </section>

        {/* ════════════ HOW IT WORKS ════════════ */}
        <section
          aria-labelledby="process-title"
          className="relative z-10 py-40 px-6 border-t"
          style={{ borderColor: "rgba(255,255,255,0.04)", background: "rgba(255,255,255,0.01)" }}
        >
          <div className="max-w-7xl mx-auto">
            <div className="text-center mb-24">
              <motion.div
                initial={{ opacity: 0 }}
                whileInView={{ opacity: 1 }}
                viewport={{ once: true }}
                className="inline-flex items-center gap-4 mb-6"
              >
                <div className="w-10 h-px bg-white/10" />
                <span className="text-[9px] font-mono text-white/30 uppercase tracking-[0.65em] font-bold">The Protocol</span>
                <div className="w-10 h-px bg-white/10" />
              </motion.div>
              <h2
                id="process-title"
                className="text-4xl md:text-6xl font-black text-white mb-5 tracking-tight"
              >
                System Workflow
              </h2>
              <p className="max-w-2xl mx-auto text-white/40 text-base leading-relaxed">
                &ldquo;Autonomous precision through decentralized specialist intelligence.&rdquo;
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              {[
                { step: "01", title: "Evidence Intake",    desc: "Upload digital media artifacts including CCTV footage, high-resolution photographs, or raw forensic metadata exports.", icon: <UploadCloud className="w-6 h-6" /> },
                { step: "02", title: "Agent Consultation", desc: "Five specialist agents process the evidence stream concurrently, independently identifying anomalies and patterns.", icon: <Globe className="w-6 h-6" /> },
                { step: "03", title: "Arbiter Synthesis",  desc: "The Council Arbiter cross-references all findings, resolves contradictions, and computes confidence scores.", icon: <Scale className="w-6 h-6" /> },
                { step: "04", title: "Signed Verdict",     desc: "A cryptographically signed forensic report is generated, providing a comprehensive and immutable authenticity log.", icon: <ShieldCheck className="w-6 h-6" /> },
              ].map((item, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 32 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.1 }}
                  className="group relative h-full flex flex-col items-center p-9 text-center rounded-2xl cursor-pointer transition-all duration-300"
                  style={{
                    background: "rgba(255,255,255,0.025)",
                    backdropFilter: "blur(16px)",
                    border: "1px solid rgba(255,255,255,0.06)",
                  }}
                  whileHover={{ y: -6 }}
                >
                  {/* Hover border glow */}
                  <div className="absolute inset-0 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none"
                    style={{ boxShadow: "inset 0 0 0 1px rgba(34,211,238,0.2), 0 0 40px rgba(34,211,238,0.06)" }} />

                  <div
                    className="mb-7 w-14 h-14 rounded-xl flex items-center justify-center text-cyan-400 transition-all duration-300 group-hover:scale-110"
                    style={{
                      background: "rgba(34,211,238,0.07)",
                      border: "1px solid rgba(34,211,238,0.15)",
                    }}
                  >
                    {item.icon}
                  </div>
                  <span className="text-[9px] font-mono text-white/25 font-bold tracking-[0.4em] uppercase mb-2">
                    PHASE {item.step}
                  </span>
                  <h3 className="text-lg font-bold text-white mb-4 group-hover:text-cyan-300 transition-colors">
                    {item.title}
                  </h3>
                  <p className="text-white/40 text-sm leading-relaxed">{item.desc}</p>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* ════════════ MEET THE COUNCIL ════════════ */}
        <section className="py-40 px-6 relative overflow-hidden">
          {/* Top divider gradient */}
          <div className="absolute top-0 left-0 w-full h-px"
            style={{ background: "linear-gradient(to right, transparent, rgba(34,211,238,0.15), transparent)" }} />

          <div className="max-w-7xl mx-auto">
            <div className="mb-24 flex flex-col items-center">
              <span className="text-[9px] font-mono text-white/25 uppercase tracking-[0.65em] font-bold mb-6">
                Autonomous Council
              </span>
              <h2 className="text-4xl md:text-6xl font-black text-white text-center leading-[0.92]">
                Meet the Agents
              </h2>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {AGENTS_DATA.map((agent, i) => (
                <motion.div
                  key={agent.id}
                  initial={{ opacity: 0, y: 40 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.08 }}
                  whileHover={{ y: -8 }}
                  className="group relative p-8 rounded-2xl cursor-pointer overflow-hidden transition-all duration-300"
                  style={{
                    background: "rgba(255,255,255,0.03)",
                    backdropFilter: "blur(20px)",
                    border: "1px solid rgba(255,255,255,0.07)",
                  }}
                >
                  {/* Hover glow overlay */}
                  <div className="absolute inset-0 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none"
                    style={{ boxShadow: "inset 0 0 0 1px rgba(34,211,238,0.18), 0 0 50px rgba(34,211,238,0.05)" }} />

                  {/* ID tag */}
                  <div className="absolute top-5 right-5 font-mono text-[9px] text-white/15 group-hover:text-cyan-400/50 transition-colors">
                    #{agent.id.toUpperCase()}
                  </div>

                  {/* Agent icon */}
                  <div
                    className="w-14 h-14 mb-9 rounded-xl flex items-center justify-center transition-all duration-500 group-hover:scale-110"
                    style={{
                      background: "rgba(34,211,238,0.06)",
                      border: "1px solid rgba(34,211,238,0.12)",
                    }}
                  >
                    <AgentIcon
                      agentId={agent.id}
                      size="lg"
                      className="text-cyan-400/40 group-hover:text-cyan-400 transition-colors duration-300"
                    />
                  </div>

                  <h3 className="text-lg font-bold text-white mb-3 group-hover:text-cyan-300 transition-colors">
                    {agent.name}
                  </h3>
                  <p className="text-white/35 text-sm leading-relaxed mb-8">{agent.desc}</p>

                  <div className="flex items-center gap-2 text-[9px] font-mono text-white/20 font-bold uppercase tracking-widest">
                    <div className="w-1.5 h-1.5 rounded-full bg-cyan-400/50 animate-pulse" />
                    Unit Active
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

      </main>

      <GlobalFooter />

      {/* ════════════ UPLOAD MODAL ════════════ */}
      <AnimatePresence>
        {modalOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.22 }}
            className="fixed inset-0 z-[200] flex items-center justify-center p-4"
            style={{ background: "rgba(3,11,26,0.75)", backdropFilter: "blur(16px)" }}
            onClick={(e) => { if (e.target === e.currentTarget) handleModalClose(); }}
          >
            <motion.div
              initial={{ scale: 0.92, opacity: 0, y: 24 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.92, opacity: 0, y: 24 }}
              transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
              className="relative w-full max-w-lg z-10 overflow-hidden rounded-2xl"
              style={{
                background: "rgba(3,11,26,0.92)",
                backdropFilter: "blur(48px)",
                border: "1px solid rgba(255,255,255,0.08)",
                boxShadow: "0 32px 80px rgba(0,0,0,0.8), 0 0 0 1px rgba(34,211,238,0.04), inset 0 1px 0 rgba(255,255,255,0.05)"
              }}
            >
              {/* Modal header */}
              <div
                className="flex items-center justify-between px-7 py-5"
                style={{
                  background: "rgba(255,255,255,0.02)",
                  borderBottom: "1px solid rgba(255,255,255,0.06)"
                }}
              >
                <div>
                  <h2 className="text-base font-black text-white tracking-tight">Evidence Intake</h2>
                  <p className="text-[9px] font-mono text-cyan-400/60 uppercase tracking-[0.35em] mt-0.5">System Phase 01</p>
                </div>
                <button
                  onClick={handleModalClose}
                  className="p-2 rounded-lg transition-colors hover:bg-white/08 cursor-pointer"
                  aria-label="Close modal"
                >
                  <X className="w-4 h-4 text-white/30 hover:text-white transition-colors" />
                </button>
              </div>

              {/* Modal body */}
              <div className="p-7">
                <AnimatePresence mode="wait">
                  {!file ? (
                    <motion.div
                      key="dz"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                    >
                      <input
                        type="file"
                        ref={fileInputRef}
                        className="sr-only"
                        accept="image/*,video/*,audio/*"
                        onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
                      />
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                        onDragLeave={() => setIsDragging(false)}
                        onDrop={(e) => {
                          e.preventDefault(); setIsDragging(false);
                          const f = e.dataTransfer.files?.[0];
                          if (f) handleFile(f);
                        }}
                        className="w-full h-52 rounded-xl border-2 border-dashed flex flex-col items-center justify-center transition-all duration-300 cursor-pointer group"
                        style={{
                          borderColor: isDragging ? "rgba(34,211,238,0.6)" : "rgba(255,255,255,0.08)",
                          background: isDragging ? "rgba(34,211,238,0.05)" : "rgba(255,255,255,0.02)",
                        }}
                        aria-label="Upload evidence file"
                      >
                        <UploadCloud
                          className="w-10 h-10 mb-4 transition-colors duration-300"
                          style={{ color: isDragging ? "#22D3EE" : "rgba(255,255,255,0.15)" }}
                          aria-hidden="true"
                        />
                        <p className="text-sm font-bold text-white/70 tracking-tight">
                          {isDragging ? "Release to upload" : "Click or drag artifacts here"}
                        </p>
                        <p className="text-[9px] text-white/25 mt-2 font-mono uppercase tracking-[0.2em]">
                          Image · Video · Audio — 50 MB max
                        </p>
                      </button>
                      {validationError && (
                        <p className="mt-4 text-rose-400 text-xs text-center font-bold tracking-tight">{validationError}</p>
                      )}
                    </motion.div>
                  ) : (
                    <motion.div
                      key="preview"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className="space-y-5"
                    >
                      <div
                        className="relative aspect-video rounded-xl overflow-hidden flex items-center justify-center"
                        style={{ background: "rgba(0,0,0,0.5)", border: "1px solid rgba(255,255,255,0.06)" }}
                      >
                        {previewUrl && file?.type.startsWith("image/") ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={previewUrl} alt="Preview" className="w-full h-full object-contain" />
                        ) : previewUrl && file?.type.startsWith("video/") ? (
                          <video src={previewUrl} className="w-full h-full object-contain" muted autoPlay loop />
                        ) : (
                          <div className="flex flex-col items-center text-white/20">
                            <File className="w-14 h-14 mb-3" />
                            <span className="text-[10px] font-mono uppercase tracking-widest">{file?.name}</span>
                          </div>
                        )}
                        <div className="absolute inset-0 bg-gradient-to-t from-black/70 to-transparent pointer-events-none" />
                        <div className="absolute bottom-4 left-5 right-5 flex items-center justify-between">
                          <span className="text-[9px] font-black text-white/80 uppercase tracking-[0.18em]">
                            {file?.type.split("/")[1]} · {((file?.size ?? 0) / 1024 / 1024).toFixed(2)} MB
                          </span>
                          <ShieldCheck className="w-4 h-4 text-cyan-400" style={{ filter: "drop-shadow(0 0 6px rgba(34,211,238,0.6))" }} />
                        </div>
                      </div>

                      <div className="flex gap-3">
                        <button
                          onClick={handleClearFile}
                          className="btn-premium-glass flex-1 py-3 justify-center"
                        >
                          Discard
                        </button>
                        <button
                          onClick={handleInitiate}
                          className="btn-premium-amber flex-1 py-3 justify-center"
                        >
                          {isTransitioning ? "Sealing Evidence…" : "Initiate Audit"}
                        </button>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
