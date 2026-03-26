"use client";

import { useRef, useState, useEffect } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  ArrowRight, ShieldCheck, UploadCloud, Cpu, Scale,
  FileSignature, Image as ImageIcon, Mic, Focus,
  Video, FileCode2, CheckCircle2, ChevronRight, Lock,
} from "lucide-react";

// ── Typewriter hook ───────────────────────────────────────────────────────────
function useTypewriter(text: string, speed = 70, delay = 500) {
  const [displayed, setDisplayed] = useState("");
  const [done, setDone] = useState(false);

  useEffect(() => {
    setDisplayed("");
    setDone(false);
    let interval: ReturnType<typeof setInterval> | undefined;
    const timeout = setTimeout(() => {
      let i = 0;
      interval = setInterval(() => {
        i++;
        setDisplayed(text.slice(0, i));
        if (i >= text.length) {
          clearInterval(interval);
          setDone(true);
        }
      }, speed);
    }, delay);
    return () => {
      clearTimeout(timeout);
      clearInterval(interval);
    };
  }, [text, speed, delay]);

  return { displayed, done };
}

// ── Data ──────────────────────────────────────────────────────────────────────
const AGENTS = [
  {
    id: "AGT-01",
    name: "Image Forensics",
    icon: ImageIcon,
    role: "Visual Authenticity",
    desc: "ELA analysis, copy-move detection, and PRNU camera noise fingerprints to expose visual splicing.",
    large: true,
  },
  {
    id: "AGT-02",
    name: "Audio Forensics",
    icon: Mic,
    role: "Acoustic Integrity",
    desc: "Wav2Vec2 deepfake detection and spectral analysis to catch voice cloning and audio splicing.",
    large: false,
  },
  {
    id: "AGT-03",
    name: "Object & Scene",
    icon: Focus,
    role: "Contextual Consistency",
    desc: "YOLOv8 lighting, shadow, and reflection anomaly detection to spot compositing errors.",
    large: false,
  },
  {
    id: "AGT-04",
    name: "Video Forensics",
    icon: Video,
    role: "Temporal Analysis",
    desc: "Frame-by-frame face-swap and temporal inconsistency scans.",
    large: false,
  },
  {
    id: "AGT-05",
    name: "Metadata",
    icon: FileCode2,
    role: "Digital Footprint",
    desc: "EXIF/XMP extraction, GPS cross-reference, solar positioning checks.",
    large: false,
  },
];

const PIPELINE = [
  {
    step: "01",
    icon: UploadCloud,
    title: "Secure Ingestion",
    desc: "File uploaded. SHA-256 hash calculated immediately to establish an immutable chain of custody.",
    tag: "CHAIN OF CUSTODY INITIATED",
  },
  {
    step: "02",
    icon: Cpu,
    title: "Multi-Agent Scan",
    desc: "Five specialized AI agents execute parallel deep-analysis loops across pixels, audio, and metadata.",
    tag: "5 AGENTS ACTIVE",
  },
  {
    step: "03",
    icon: Scale,
    title: "Council Deliberation",
    desc: "The Arbiter cross-references all agent findings, resolves conflicts, and synthesizes a unified confidence score.",
    tag: "CONFLICT RESOLUTION",
  },
  {
    step: "04",
    icon: FileSignature,
    title: "Cryptographic Verdict",
    desc: "Tamper-evident ECDSA P-256 signed forensic report — court-admissible and immutable.",
    tag: "VERDICT SIGNED",
  },
];

const ICON_POSITIONS = [
  { angle: -90 },
  { angle: -18 },
  { angle: 54 },
  { angle: 126 },
  { angle: 198 },
];

// ── Component ─────────────────────────────────────────────────────────────────
export default function LandingPage() {
  const { displayed, done } = useTypewriter("FORENSIC COUNCIL", 75, 600);
  const pipelineRef = useRef<HTMLDivElement>(null);

  return (
    <div
      className="min-h-screen relative overflow-x-hidden"
      style={{ backgroundColor: "#000A14", fontFamily: "var(--font-poppins), sans-serif" }}
    >
      {/* HUD grid background */}
      <div
        className="fixed inset-0 pointer-events-none"
        aria-hidden="true"
        style={{
          backgroundImage:
            "linear-gradient(to right,rgba(0,255,255,0.03) 1px,transparent 1px)," +
            "linear-gradient(to bottom,rgba(0,255,255,0.03) 1px,transparent 1px)",
          backgroundSize: "60px 60px",
        }}
      />

      {/* Ambient glow */}
      <div
        className="fixed top-0 left-1/2 -translate-x-1/2 pointer-events-none"
        aria-hidden="true"
        style={{
          width: "900px",
          height: "400px",
          background:
            "radial-gradient(ellipse at center, rgba(0,255,255,0.05) 0%, transparent 70%)",
        }}
      />

      {/* ── Navbar ── */}
      <nav
        aria-label="Main navigation"
        className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-8 py-5"
        style={{
          borderBottom: "1px solid rgba(0,255,255,0.08)",
          backgroundColor: "rgba(0,10,20,0.85)",
          backdropFilter: "blur(20px)",
        }}
      >
        <div className="flex items-center gap-3">
          <div
            className="p-2 rounded-lg"
            style={{
              backgroundColor: "rgba(0,255,255,0.05)",
              border: "1px solid rgba(0,255,255,0.15)",
            }}
          >
            <ShieldCheck className="w-5 h-5" style={{ color: "#00FFFF" }} aria-hidden="true" />
          </div>
          <span
            className="text-base font-semibold tracking-[0.18em] text-white"
            style={{ fontFamily: "var(--font-fira-code), monospace" }}
          >
            FORENSIC COUNCIL
          </span>
        </div>

        <Link
          href="/evidence"
          className="hidden md:inline-flex items-center gap-2 px-5 py-2 rounded text-sm font-medium tracking-widest transition-all duration-200 cursor-pointer"
          style={{
            color: "#00FFFF",
            border: "1px solid rgba(0,255,255,0.3)",
            backgroundColor: "rgba(0,255,255,0.05)",
            fontFamily: "var(--font-fira-code), monospace",
          }}
        >
          INITIATE ANALYSIS
          <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
        </Link>
      </nav>

      {/* ── Hero ── */}
      <section className="relative min-h-screen flex flex-col items-center justify-center pt-20 pb-16 px-6 text-center">

        {/* Status badge */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="inline-flex items-center gap-2 px-4 py-1.5 mb-12 rounded text-xs tracking-[0.2em]"
          style={{
            border: "1px solid rgba(34,197,94,0.3)",
            backgroundColor: "rgba(34,197,94,0.05)",
            color: "#22C55E",
            fontFamily: "var(--font-fira-code), monospace",
          }}
        >
          <span
            className="w-1.5 h-1.5 rounded-full animate-pulse"
            style={{ backgroundColor: "#22C55E" }}
            aria-hidden="true"
          />
          SYSTEM STATUS: OPERATIONAL
        </motion.div>

        {/* Typewriter title */}
        <h1
          className="text-5xl md:text-7xl lg:text-8xl font-bold tracking-[0.12em] mb-4 min-h-[1.2em]"
          style={{
            color: "#00FFFF",
            textShadow: "0 0 40px rgba(0,255,255,0.25)",
            fontFamily: "var(--font-fira-code), monospace",
          }}
          aria-label="FORENSIC COUNCIL"
        >
          {displayed}
          {!done && (
            <span className="animate-pulse" aria-hidden="true">
              _
            </span>
          )}
        </h1>

        {/* Subtitle */}
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: done ? 1 : 0 }}
          transition={{ duration: 0.8 }}
          className="text-sm md:text-base tracking-[0.3em] uppercase mb-4"
          style={{
            color: "rgba(255,255,255,0.35)",
            fontFamily: "var(--font-fira-code), monospace",
          }}
        >
          Multi-Agent Forensic Evidence Analysis
        </motion.p>

        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: done ? 1 : 0 }}
          transition={{ duration: 0.8, delay: 0.15 }}
          className="text-lg md:text-xl text-white/60 max-w-lg mb-14 font-light leading-relaxed"
        >
          5 independent AI agents. 1 cryptographically signed verdict.
        </motion.p>

        {/* Agent network visualization */}
        <motion.div
          className="relative mb-14"
          style={{ width: 256, height: 256 }}
          aria-hidden="true"
          initial={{ opacity: 0, scale: 0.92 }}
          animate={{ opacity: done ? 1 : 0, scale: done ? 1 : 0.92 }}
          transition={{ duration: 0.8, delay: 0.3 }}
        >
          {/* SVG lines */}
          <svg className="absolute inset-0 w-full h-full" viewBox="0 0 256 256">
            {/* Outer ring */}
            <circle
              cx="128" cy="128" r="100"
              fill="none"
              stroke="rgba(0,255,255,0.08)"
              strokeWidth="1"
              strokeDasharray="4 6"
            />
            {/* Connecting lines */}
            {ICON_POSITIONS.map((pos, i) => {
              const rad = (pos.angle * Math.PI) / 180;
              return (
                <motion.line
                  key={i}
                  x1="128" y1="128"
                  x2={128 + 100 * Math.cos(rad)}
                  y2={128 + 100 * Math.sin(rad)}
                  stroke="rgba(0,255,255,0.15)"
                  strokeWidth="1"
                  strokeDasharray="3 4"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.5 + i * 0.1, duration: 0.4 }}
                />
              );
            })}
          </svg>

          {/* Center node — Arbiter */}
          <div
            className="absolute flex items-center justify-center rounded-full"
            style={{
              top: "50%", left: "50%",
              transform: "translate(-50%, -50%)",
              width: 56, height: 56,
              backgroundColor: "rgba(0,255,255,0.1)",
              border: "1px solid rgba(0,255,255,0.45)",
              boxShadow: "0 0 24px rgba(0,255,255,0.15)",
              zIndex: 10,
            }}
          >
            <ShieldCheck className="w-6 h-6" style={{ color: "#00FFFF" }} aria-label="Council Arbiter" />
          </div>

          {/* Agent nodes */}
          {AGENTS.map((agent, i) => {
            const rad = (ICON_POSITIONS[i].angle * Math.PI) / 180;
            const x = 50 + (100 / 256) * 100 * Math.cos(rad);
            const y = 50 + (100 / 256) * 100 * Math.sin(rad);
            return (
              <motion.div
                key={agent.id}
                className="absolute flex items-center justify-center rounded-full"
                style={{
                  left: `${x}%`, top: `${y}%`,
                  transform: "translate(-50%, -50%)",
                  width: 36, height: 36,
                  backgroundColor: "rgba(0,255,255,0.07)",
                  border: "1px solid rgba(0,255,255,0.25)",
                  zIndex: 10,
                }}
                initial={{ scale: 0, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ delay: 0.55 + i * 0.12, type: "spring", stiffness: 220 }}
                title={agent.name}
              >
                <agent.icon className="w-3.5 h-3.5" style={{ color: "#00FFFF" }} aria-hidden="true" />
              </motion.div>
            );
          })}
        </motion.div>

        {/* CTA */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: done ? 1 : 0, y: done ? 0 : 10 }}
          transition={{ duration: 0.5, delay: 0.5 }}
        >
          <Link
            href="/evidence"
            className="group inline-flex items-center gap-3 px-8 py-4 rounded text-sm font-semibold tracking-[0.2em] transition-all duration-200 cursor-pointer"
            style={{
              color: "#000A14",
              backgroundColor: "#00FFFF",
              boxShadow: "0 0 35px rgba(0,255,255,0.25)",
              fontFamily: "var(--font-fira-code), monospace",
            }}
          >
            INITIATE ANALYSIS
            <ArrowRight className="w-4 h-4 transition-transform duration-200 group-hover:translate-x-1" aria-hidden="true" />
          </Link>
        </motion.div>
      </section>

      {/* ── Bento Grid — Agents ── */}
      <section
        className="relative py-24 px-6 z-10"
        aria-labelledby="agents-heading"
        style={{ borderTop: "1px solid rgba(0,255,255,0.06)" }}
      >
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <p
              className="text-xs tracking-[0.3em] mb-3"
              style={{ color: "rgba(0,255,255,0.55)", fontFamily: "var(--font-fira-code), monospace" }}
            >
              COGNITIVE ARCHITECTURE
            </p>
            <h2 id="agents-heading" className="text-3xl md:text-5xl font-bold text-white">
              Six Profiles. One Truth.
            </h2>
          </div>

          <div className="grid grid-cols-12 gap-4">

            {/* Large card — Agent 1 */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ delay: 0 }}
              className="col-span-12 md:col-span-5 p-8 rounded-2xl relative overflow-hidden group"
              style={{
                backgroundColor: "rgba(0,20,40,0.7)",
                border: "1px solid rgba(0,255,255,0.1)",
                backdropFilter: "blur(16px)",
                minHeight: 260,
              }}
            >
              <div
                className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none"
                style={{ background: "radial-gradient(circle at 30% 30%, rgba(0,255,255,0.04), transparent 60%)" }}
                aria-hidden="true"
              />
              <span
                className="text-xs tracking-widest mb-5 block"
                style={{ color: "rgba(0,255,255,0.45)", fontFamily: "var(--font-fira-code), monospace" }}
              >
                AGT-01
              </span>
              <div
                className="p-3 rounded-xl w-fit mb-5"
                style={{ backgroundColor: "rgba(0,255,255,0.08)", border: "1px solid rgba(0,255,255,0.15)" }}
              >
                <ImageIcon className="w-7 h-7" style={{ color: "#00FFFF" }} aria-hidden="true" />
              </div>
              <h3 className="text-xl font-bold text-white mb-1">Image Forensics</h3>
              <p
                className="text-xs mb-4"
                style={{ color: "rgba(0,255,255,0.55)", fontFamily: "var(--font-fira-code), monospace" }}
              >
                Visual Authenticity
              </p>
              <p className="text-sm text-slate-400 leading-relaxed">
                Analyzes Error Level Analysis (ELA), copy-move artifacts, and PRNU camera noise fingerprints to detect visual splicing and compositing.
              </p>
            </motion.div>

            {/* 4 smaller cards */}
            {AGENTS.slice(1).map((agent, idx) => (
              <motion.div
                key={agent.id}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-60px" }}
                transition={{ delay: 0.08 * (idx + 1) }}
                className={`col-span-12 ${idx < 2 ? "sm:col-span-6 md:col-span-4" : "sm:col-span-6 md:col-span-4"} p-6 rounded-2xl relative overflow-hidden group`}
                style={{
                  backgroundColor: "rgba(0,20,40,0.7)",
                  border: "1px solid rgba(0,255,255,0.1)",
                  backdropFilter: "blur(16px)",
                }}
              >
                <div
                  className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none"
                  style={{ background: "radial-gradient(circle at 30% 30%, rgba(0,255,255,0.04), transparent 60%)" }}
                  aria-hidden="true"
                />
                <span
                  className="text-xs tracking-widest mb-4 block"
                  style={{ color: "rgba(0,255,255,0.45)", fontFamily: "var(--font-fira-code), monospace" }}
                >
                  {agent.id}
                </span>
                <div
                  className="p-2.5 rounded-lg w-fit mb-4"
                  style={{ backgroundColor: "rgba(0,255,255,0.08)", border: "1px solid rgba(0,255,255,0.15)" }}
                >
                  <agent.icon className="w-5 h-5" style={{ color: "#00FFFF" }} aria-hidden="true" />
                </div>
                <h3 className="text-base font-bold text-white mb-1">{agent.name}</h3>
                <p
                  className="text-xs mb-3"
                  style={{ color: "rgba(0,255,255,0.55)", fontFamily: "var(--font-fira-code), monospace" }}
                >
                  {agent.role}
                </p>
                <p className="text-xs text-slate-400 leading-relaxed">{agent.desc}</p>
              </motion.div>
            ))}

            {/* Council Arbiter — full-width accent card */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ delay: 0.3 }}
              className="col-span-12 p-8 rounded-2xl relative overflow-hidden"
              style={{
                background: "linear-gradient(135deg, rgba(0,255,255,0.07) 0%, rgba(0,20,40,0.85) 100%)",
                border: "1px solid rgba(0,255,255,0.2)",
                backdropFilter: "blur(16px)",
              }}
            >
              <div className="flex flex-col md:flex-row md:items-center gap-6">
                <div className="flex-shrink-0">
                  <span
                    className="text-xs tracking-widest mb-3 block"
                    style={{ color: "rgba(0,255,255,0.65)", fontFamily: "var(--font-fira-code), monospace" }}
                  >
                    ARB-01
                  </span>
                  <div
                    className="p-3 rounded-xl w-fit"
                    style={{
                      backgroundColor: "rgba(0,255,255,0.1)",
                      border: "1px solid rgba(0,255,255,0.3)",
                      boxShadow: "0 0 20px rgba(0,255,255,0.08)",
                    }}
                  >
                    <ShieldCheck className="w-8 h-8" style={{ color: "#00FFFF" }} aria-hidden="true" />
                  </div>
                </div>
                <div className="flex-1">
                  <h3 className="text-xl font-bold text-white mb-1">Council Arbiter</h3>
                  <p
                    className="text-xs mb-3"
                    style={{ color: "rgba(0,255,255,0.55)", fontFamily: "var(--font-fira-code), monospace" }}
                  >
                    Final Synthesis — ECDSA P-256 Signed
                  </p>
                  <p className="text-sm text-slate-300 leading-relaxed max-w-3xl">
                    Cross-references all five agent findings, resolves conflicts, and synthesizes a unified confidence score into a single cohesive, cryptographically signed court-admissible forensic narrative.
                  </p>
                </div>
                <div
                  className="hidden md:block flex-shrink-0 text-right text-xs"
                  style={{ color: "rgba(0,255,255,0.35)", fontFamily: "var(--font-fira-code), monospace", lineHeight: 2 }}
                  aria-hidden="true"
                >
                  <div>SIG_ALG: ECDSA-P256</div>
                  <div>STATUS: VERIFIED</div>
                  <div style={{ color: "#22C55E" }}>CHAIN: INTACT</div>
                </div>
              </div>
            </motion.div>

          </div>
        </div>
      </section>

      {/* ── Pipeline — Horizontal Scroll ── */}
      <section
        className="relative py-24 z-10"
        aria-labelledby="pipeline-heading"
        style={{ borderTop: "1px solid rgba(0,255,255,0.06)" }}
      >
        <div className="max-w-6xl mx-auto px-6 mb-10">
          <p
            className="text-xs tracking-[0.3em] mb-3"
            style={{ color: "rgba(0,255,255,0.55)", fontFamily: "var(--font-fira-code), monospace" }}
          >
            FORENSIC PIPELINE
          </p>
          <h2 id="pipeline-heading" className="text-3xl md:text-5xl font-bold text-white">
            From Upload to Verdict.
          </h2>
        </div>

        <div
          ref={pipelineRef}
          className="flex gap-4 px-6 pb-6 overflow-x-auto"
          style={{ scrollbarWidth: "none", msOverflowStyle: "none" }}
          role="list"
          aria-label="Investigation pipeline steps"
        >
          {PIPELINE.map((step, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: 30 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{ delay: i * 0.08 }}
              className="relative flex-none w-72 p-8 rounded-2xl"
              style={{
                backgroundColor: "rgba(0,20,40,0.7)",
                border: "1px solid rgba(0,255,255,0.1)",
                backdropFilter: "blur(16px)",
              }}
              role="listitem"
            >
              {/* Large step number */}
              <div
                className="text-8xl font-bold leading-none mb-5 select-none"
                style={{ color: "rgba(0,255,255,0.05)", fontFamily: "var(--font-fira-code), monospace" }}
                aria-hidden="true"
              >
                {step.step}
              </div>

              <div
                className="p-2.5 rounded-lg w-fit mb-4"
                style={{ backgroundColor: "rgba(0,255,255,0.08)", border: "1px solid rgba(0,255,255,0.15)" }}
              >
                <step.icon className="w-5 h-5" style={{ color: "#00FFFF" }} aria-hidden="true" />
              </div>

              <h3 className="text-lg font-bold text-white mb-3">{step.title}</h3>
              <p className="text-sm text-slate-400 leading-relaxed mb-6">{step.desc}</p>

              <div
                className="inline-flex items-center gap-1.5 px-3 py-1 rounded text-xs tracking-widest"
                style={{
                  backgroundColor: "rgba(0,255,255,0.05)",
                  border: "1px solid rgba(0,255,255,0.12)",
                  color: "rgba(0,255,255,0.6)",
                  fontFamily: "var(--font-fira-code), monospace",
                }}
              >
                {step.tag}
              </div>

              {/* Arrow connector */}
              {i < PIPELINE.length - 1 && (
                <div
                  className="absolute -right-3 top-1/2 -translate-y-1/2 z-10 w-6 h-6 rounded-full flex items-center justify-center"
                  style={{ backgroundColor: "#000A14", border: "1px solid rgba(0,255,255,0.2)" }}
                  aria-hidden="true"
                >
                  <ChevronRight className="w-3 h-3" style={{ color: "#00FFFF" }} />
                </div>
              )}
            </motion.div>
          ))}

          {/* Final CTA card */}
          <motion.div
            initial={{ opacity: 0, x: 30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true, margin: "-40px" }}
            transition={{ delay: 0.32 }}
            className="flex-none w-60 rounded-2xl flex flex-col items-center justify-center text-center p-8"
            style={{
              background: "linear-gradient(135deg, rgba(0,255,255,0.09), rgba(0,20,40,0.5))",
              border: "1px solid rgba(0,255,255,0.18)",
            }}
          >
            <Lock className="w-10 h-10 mb-4" style={{ color: "#00FFFF" }} aria-hidden="true" />
            <h3 className="text-base font-bold text-white mb-5">Ready to analyze?</h3>
            <Link
              href="/evidence"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded text-sm font-semibold tracking-wider transition-colors duration-200 cursor-pointer"
              style={{
                backgroundColor: "#00FFFF",
                color: "#000A14",
                fontFamily: "var(--font-fira-code), monospace",
              }}
            >
              BEGIN
              <ArrowRight className="w-4 h-4" aria-hidden="true" />
            </Link>
          </motion.div>
        </div>
      </section>

      {/* ── Trust — Mock Signed Report ── */}
      <section
        className="relative py-24 px-6 z-10"
        aria-labelledby="trust-heading"
        style={{ borderTop: "1px solid rgba(0,255,255,0.06)" }}
      >
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-12">
            <p
              className="text-xs tracking-[0.3em] mb-3"
              style={{ color: "rgba(0,255,255,0.55)", fontFamily: "var(--font-fira-code), monospace" }}
            >
              CRYPTOGRAPHIC TRUST
            </p>
            <h2 id="trust-heading" className="text-3xl md:text-5xl font-bold text-white mb-4">
              Every Report is Signed.
            </h2>
            <p className="text-slate-400 max-w-lg mx-auto text-sm leading-relaxed">
              ECDSA P-256 signatures ensure your forensic report cannot be altered after generation. Verifiable by any standards-compliant tool.
            </p>
          </div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-60px" }}
            className="p-8 rounded-2xl"
            style={{
              backgroundColor: "rgba(0,20,40,0.8)",
              border: "1px solid rgba(0,255,255,0.14)",
              backdropFilter: "blur(16px)",
              fontFamily: "var(--font-fira-code), monospace",
            }}
            role="region"
            aria-label="Sample forensic report"
          >
            {/* Header row */}
            <div
              className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 pb-6"
              style={{ borderBottom: "1px solid rgba(0,255,255,0.1)" }}
            >
              <div>
                <div
                  className="text-xs tracking-widest mb-1"
                  style={{ color: "rgba(0,255,255,0.45)" }}
                >
                  FORENSIC COUNCIL — SIGNED REPORT
                </div>
                <div className="text-white font-semibold text-base">evidence_sample_001.mp4</div>
              </div>
              <div
                className="inline-flex items-center gap-2 px-4 py-2 rounded"
                style={{
                  backgroundColor: "rgba(34,197,94,0.09)",
                  border: "1px solid rgba(34,197,94,0.3)",
                }}
              >
                <CheckCircle2 className="w-4 h-4 flex-shrink-0" style={{ color: "#22C55E" }} aria-hidden="true" />
                <span className="text-sm font-medium" style={{ color: "#22C55E" }}>
                  SIGNATURE VALID
                </span>
              </div>
            </div>

            {/* Report fields */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-4 mb-6">
              {[
                { label: "FILE_HASH (SHA-256)", value: "e3b0c44298fc1c149afbf4c899..." },
                { label: "VERDICT", value: "AUTHENTIC — 97.4% confidence", green: true },
                { label: "AGENTS_QUERIED", value: "5 / 5 — all returned findings", green: true },
                { label: "TIMESTAMP", value: "2026-03-26T09:41:00Z" },
                { label: "SIGNATURE_ALG", value: "ECDSA-P256-SHA256" },
                { label: "REPORT_ID", value: "FC-20260326-a1f3d9b2" },
              ].map((f) => (
                <div key={f.label}>
                  <div
                    className="text-xs mb-1"
                    style={{ color: "rgba(0,255,255,0.4)" }}
                  >
                    {f.label}
                  </div>
                  <div
                    className="text-sm truncate"
                    style={{ color: f.green ? "#22C55E" : "rgba(255,255,255,0.75)" }}
                  >
                    {f.value}
                  </div>
                </div>
              ))}
            </div>

            {/* Signature block */}
            <div
              className="p-4 rounded-lg"
              style={{ backgroundColor: "rgba(0,0,0,0.35)", border: "1px solid rgba(0,255,255,0.07)" }}
            >
              <div
                className="text-xs mb-2"
                style={{ color: "rgba(0,255,255,0.4)" }}
              >
                DIGITAL_SIGNATURE
              </div>
              <div
                className="text-xs break-all leading-relaxed"
                style={{ color: "rgba(255,255,255,0.25)" }}
                aria-label="Sample digital signature"
              >
                MEUCIQDv8X7zK2mN4pLq9R1jF3bW0sE6cH5tY8uA2oI7xP3vDwIgNz4KmB1aT6wR9hC2...
              </div>
            </div>
          </motion.div>
        </div>
      </section>

    </div>
  );
}
