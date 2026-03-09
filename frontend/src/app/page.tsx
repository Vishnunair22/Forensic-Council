"use client";

import { motion, AnimatePresence } from "framer-motion";
import { ChevronRight, ShieldCheck, File, UploadCloud, FileImage, FileAudio, FileVideo, X, ArrowRight, RotateCcw } from "lucide-react";

import { useEffect, useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { AGENTS_DATA } from "@/lib/constants";
import { AgentIcon } from "@/components/ui/AgentIcon";
import { useSound } from "@/hooks/useSound";

export default function LandingPage() {
  const { playSound } = useSound();
  const router = useRouter();
  const [modalOpen, setModalOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback((f: File) => {
    if (f.size > 50 * 1024 * 1024) {
      setValidationError("File must be under 50MB");
      playSound("error");
      return;
    }
    setValidationError(null);
    setFile(f);
    if (f.type.startsWith("image/") || f.type.startsWith("video/")) {
      const url = URL.createObjectURL(f);
      setPreviewUrl(url);
    } else {
      setPreviewUrl(null);
    }
    playSound("success");
  }, [playSound]);

  const handleClearFile = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(null);
    setPreviewUrl(null);
    setValidationError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const [isTransitioning, setIsTransitioning] = useState(false);

  const handleInitiate = () => {
    if (!file || isTransitioning) return;
    setIsTransitioning(true);
    playSound("upload");
    sessionStorage.setItem("forensic_pending_file_name", file.name);
    sessionStorage.setItem("forensic_auto_start", "true");
    (window as { __forensic_pending_file?: File }).__forensic_pending_file = file;
    // Don't close modal immediately, wait for route transition to start
    router.push("/evidence");
  };

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  // Force scroll to top on mount
  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  return (
    <div className="relative bg-[#050505] text-white overflow-x-hidden">
      {/* Global Background Elements */}
      <div className="fixed inset-0 z-0 pointer-events-none" aria-hidden="true">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff05_1px,transparent_1px),linear-gradient(to_bottom,#ffffff05_1px,transparent_1px)] bg-[size:32px_32px]"></div>
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[500px] bg-cyan-900/20 rounded-full blur-[120px] mix-blend-screen"></div>
        <div className="absolute bottom-0 left-0 w-[500px] h-[500px] bg-purple-900/10 rounded-full blur-[100px] mix-blend-screen"></div>
      </div>

      <header className="fixed top-0 w-full p-6 flex items-center justify-between border-b border-white/5 bg-black/40 backdrop-blur-xl z-50">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 bg-gradient-to-br from-cyan-400 to-blue-600 rounded flex items-center justify-center font-bold text-slate-900 shadow-[0_0_15px_rgba(34,211,238,0.4)]">FC</div>
          <span className="text-xl font-bold tracking-tight bg-gradient-to-r from-white to-slate-400 bg-clip-text text-transparent">Forensic Council</span>
        </div>
      </header>

      {/* --- Hero Section --- */}
      <section className="relative w-full min-h-screen flex flex-col items-center justify-center px-6 pt-20 z-10 overflow-hidden">
        {/* Microscope stage plate */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[520px] h-[520px]">
          {/* Outer ring */}
          <div className="absolute inset-0 rounded-full border border-cyan-500/10" />
          {/* Middle ring - dashed */}
          <div className="absolute inset-[60px] rounded-full border border-cyan-500/15 border-dashed animate-[spin_40s_linear_infinite]" />
          {/* Inner ring */}
          <div className="absolute inset-[120px] rounded-full border border-cyan-500/20" />
          {/* Core specimen dot */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-cyan-400 shadow-[0_0_20px_rgba(34,211,238,0.8)] animate-pulse" />
          {/* Crosshair lines */}
          <div className="absolute top-1/2 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-cyan-400/30 to-transparent -translate-y-1/2" />
          <div className="absolute left-1/2 top-0 bottom-0 w-[1px] bg-gradient-to-b from-transparent via-cyan-400/30 to-transparent -translate-x-1/2" />
          {/* Corner brackets (forensic microscope reticle) */}
          {[
            "top-[58px] left-[58px] border-t border-l",
            "top-[58px] right-[58px] border-t border-r",
            "bottom-[58px] left-[58px] border-b border-l",
            "bottom-[58px] right-[58px] border-b border-r",
          ].map((cls, i) => (
            <div key={i} className={`absolute w-6 h-6 border-cyan-400/40 ${cls}`} />
          ))}
        </div>
        {/* Scanning beam — sweeps horizontally across the stage */}
        <motion.div
          animate={{ left: ["-10%", "110%"] }}
          transition={{ duration: 4, ease: "easeInOut", repeat: Infinity, repeatDelay: 1.5 }}
          className="absolute top-[28%] w-[200px] h-[44%] bg-gradient-to-r from-transparent via-cyan-400/8 to-transparent blur-sm pointer-events-none"
        />
        {/* Scan line — thin bright line that moves */}
        <motion.div
          animate={{ top: ["28%", "72%", "28%"] }}
          transition={{ duration: 3.5, ease: "linear", repeat: Infinity }}
          className="absolute left-[30%] right-[30%] h-[1.5px] bg-gradient-to-r from-transparent via-cyan-300/60 to-transparent shadow-[0_0_8px_rgba(34,211,238,0.5)]"
        />
        {/* Floating data readout tags */}
        {[
          { label: "ELA", val: "0.023", x: "left-[18%]", y: "top-[35%]", delay: 0 },
          { label: "PRNU", val: "MATCH", x: "right-[17%]", y: "top-[42%]", delay: 0.8 },
          { label: "GPS", val: "34.05°N", x: "left-[20%]", y: "bottom-[32%]", delay: 0.4 },
          { label: "SHA", val: "a9f2...", x: "right-[19%]", y: "bottom-[28%]", delay: 1.2 },
        ].map((tag, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0 }}
            animate={{ opacity: [0, 0.7, 0.7, 0] }}
            transition={{ delay: tag.delay, duration: 4, repeat: Infinity, repeatDelay: 2 }}
            className={`absolute ${tag.x} ${tag.y} font-mono text-[10px] text-cyan-400/70 bg-black/60 border border-cyan-500/20 px-2 py-1 rounded backdrop-blur-sm`}
          >
            <span className="text-cyan-500/50 mr-1">{tag.label}</span>{tag.val}
          </motion.div>
        ))}
        {/* Vignette */}
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,rgba(5,5,5,1)_80%)] z-20" />

        <div className="flex flex-col items-center justify-center text-center max-w-5xl mx-auto relative z-30">
          <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.8, ease: "easeOut" }} className="mb-6 inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/5 border border-white/10 text-sm text-cyan-400 backdrop-blur-md">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500"></span>
            </span>
            System Online
          </motion.div>
          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: "easeOut" }}
            className="text-4xl sm:text-5xl md:text-7xl font-extrabold mb-6 tracking-tighter text-transparent bg-clip-text bg-gradient-to-b from-white to-slate-400 drop-shadow-sm pb-2"
          >
            Multi-Agent Forensic Evidence Analysis System
          </motion.h1>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2, duration: 0.8 }}
            className="text-slate-300 text-base sm:text-xl max-w-2xl mb-10 leading-relaxed font-light"
          >
            This system leverages multiple specialized intelligent agents that independently analyze digital forensic evidence and synthesize their findings into a cohesive, court-ready report.
          </motion.p>
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}>
            <button
              onClick={() => { playSound("upload"); setModalOpen(true); }}
              className="group relative px-10 py-5 bg-gradient-to-r from-emerald-500 to-cyan-500 text-white text-lg font-bold rounded-full overflow-hidden transition-all hover:scale-105 hover:shadow-[0_0_60px_rgba(16,185,129,0.5)] border border-white/20 inline-flex items-center focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-cyan-500"
            >
              <span className="relative z-10 flex items-center">
                Begin Analysis <ChevronRight aria-hidden="true" className="ml-2 w-6 h-6 group-hover:translate-x-2 transition-transform" />
              </span>
            </button>
          </motion.div>
        </div>
      </section>

      {/* --- How it Works ---  */}
      <section className="relative z-10 py-32 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-20">
            <h2 className="text-3xl md:text-5xl font-bold bg-white bg-clip-text text-transparent">How Forensic Council Works</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-8 relative">
            {/* Connecting line for desktop */}
            <div className="hidden md:block absolute top-[60px] left-[10%] right-[10%] h-[1px] bg-gradient-to-r from-transparent via-cyan-500/50 to-transparent"></div>

            {[
              { step: "01", title: "Evidence Intake", desc: "Upload digital media artifacts including CCTV, photographs, or raw extracted metadata." },
              { step: "02", title: "Agent Consultation", desc: "Specialized analytical agents process the data stream concurrently, identifying anomalies." },
              { step: "03", title: "Arbiter Synthesis", desc: "The Council Arbiter evaluates findings, resolving contradictions and calculating confidence scores." },
              { step: "04", title: "Final Verdict", desc: "A cryptographically signed final report is generated, detailing the forensic analysis." }
            ].map((item, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.2, duration: 0.6 }}
                className="relative p-8 rounded-3xl 
                  bg-white/[0.03] 
                  border border-white/[0.08] 
                  backdrop-blur-2xl 
                  flex flex-col items-center text-center mt-6 group 
                  hover:border-cyan-500/30 
                  hover:bg-cyan-400/[0.04]
                  hover:shadow-[0_0_40px_rgba(34,211,238,0.06),inset_0_1px_0_rgba(255,255,255,0.05)]
                  transition-all duration-500 overflow-visible
                  shadow-[0_4px_24px_rgba(0,0,0,0.4),inset_0_1px_0_rgba(255,255,255,0.04)]"
              >
                {/* Glass shine */}
                <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/20 to-transparent" />
                <div className="absolute inset-0 rounded-3xl bg-gradient-to-b from-white/[0.03] to-transparent pointer-events-none" />
                <div className="absolute -top-8 w-16 h-16 rounded-full bg-[#050505] border border-cyan-500/30 flex items-center justify-center font-mono text-xl text-cyan-400 font-bold shadow-[0_0_20px_rgba(34,211,238,0.15)] group-hover:scale-110 transition-transform z-10" aria-hidden="true">
                  {item.step}
                </div>
                <h3 className="text-xl font-bold mb-4 mt-6 text-white relative z-10">{item.title}</h3>
                <p className="text-slate-300 text-sm leading-relaxed font-normal relative z-10">{item.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* --- Meet the Agents ---  */}
      <section className="relative z-10 pb-32 pt-16 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-5xl font-bold mb-6 bg-gradient-to-r from-cyan-400 to-purple-400 bg-clip-text text-transparent inline-block">Meet the Council</h2>
            <p className="text-slate-400 text-lg max-w-2xl mx-auto font-light">Five specialist agents analyze evidence independently, then the Council Arbiter synthesizes their findings into a unified verdict.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {AGENTS_DATA.map((agent, i) => (
              <motion.div
                key={agent.id}
                initial={{ opacity: 0, y: 40 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-100px" }}
                transition={{ delay: i * 0.1, duration: 0.6, ease: "easeOut" }}
                whileHover={{ y: -8, scale: 1.02 }}
                className="p-8 rounded-3xl 
                  bg-gradient-to-br from-white/[0.04] to-black/60
                  backdrop-blur-3xl 
                  border border-white/[0.08]
                  hover:border-cyan-400/30
                  flex flex-col items-center text-center 
                  transition-all duration-500 
                  shadow-[0_8px_32px_rgba(0,0,0,0.5),inset_0_1px_0_rgba(255,255,255,0.06)]
                  hover:shadow-[0_8px_48px_rgba(34,211,238,0.12),inset_0_1px_0_rgba(255,255,255,0.08)]
                  group relative overflow-hidden"
              >
                {/* Prismatic top shine */}
                <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/25 to-transparent" />
                <div className="absolute inset-x-0 top-0 h-20 bg-gradient-to-b from-white/[0.03] to-transparent pointer-events-none rounded-t-3xl" />
                <div className="p-4 bg-cyan-500/10 text-cyan-400 rounded-2xl mb-6 shadow-[inset_0_0_20px_rgba(34,211,238,0.05)] border border-cyan-500/20 relative z-10" aria-hidden="true">
                  <AgentIcon role={agent.role} />
                </div>
                <h3 className="text-xl font-semibold mb-2 text-white relative z-10">{agent.name}</h3>
                <span className="text-[11px] px-3 py-1 rounded-full bg-cyan-950/50 text-cyan-300 border border-cyan-500/20 uppercase tracking-widest font-semibold mb-4 relative z-10">{agent.role}</span>
                <p className="text-sm text-slate-300 leading-relaxed mb-6 font-normal relative z-10 flex-1">{agent.desc}</p>
                <div className="w-full pt-4 border-t border-white/5 relative z-10">
                  <p className="text-xs text-cyan-500 font-mono italic leading-relaxed">&quot;{agent.simulation.thinking}&quot;</p>
                </div>
              </motion.div>
            ))}

            {/* Council Arbiter Card */}
            <motion.div
              initial={{ opacity: 0, y: 40 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-100px" }}
              transition={{ delay: 0.5, duration: 0.6, ease: "easeOut" }}
              whileHover={{ y: -8, scale: 1.02 }}
              className="p-8 rounded-3xl 
                bg-gradient-to-br from-purple-500/[0.08] to-black/70
                backdrop-blur-3xl 
                border border-purple-500/30
                hover:border-purple-400/50
                flex flex-col items-center text-center 
                transition-all duration-500
                shadow-[0_8px_40px_rgba(168,85,247,0.15),inset_0_1px_0_rgba(168,85,247,0.15)]
                hover:shadow-[0_8px_60px_rgba(168,85,247,0.3),inset_0_1px_0_rgba(168,85,247,0.2)]
                group relative overflow-hidden"
            >
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(168,85,247,0.15),transparent_50%)]" aria-hidden="true"></div>
              <div className="p-4 bg-purple-500/20 text-purple-300 rounded-2xl mb-6 shadow-[inset_0_0_20px_rgba(168,85,247,0.1)] border border-purple-500/30 relative z-10 group-hover:scale-110 transition-transform duration-500" aria-hidden="true">
                <ShieldCheck className="w-8 h-8" />
              </div>
              <h3 className="text-xl font-bold mb-2 text-white relative z-10 drop-shadow-[0_0_10px_rgba(168,85,247,0.5)]">Council Arbiter</h3>
              <span className="text-[11px] px-3 py-1 rounded-full bg-purple-900/50 text-purple-300 border border-purple-500/30 uppercase tracking-widest font-bold mb-4 relative z-10">Final Verdict</span>
              <p className="text-sm text-slate-300 leading-relaxed mb-6 font-normal relative z-10 flex-1">Cross-references all agent findings, resolves contradictions via tribunal, and produces the cryptographically signed forensic report.</p>
              <div className="w-full pt-4 border-t border-purple-500/20 relative z-10">
                <p className="text-xs text-purple-400/90 font-mono italic leading-relaxed">&quot;Synthesizing cross-modal evidence and resolving logical conflicts...&quot;</p>
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      {/* --- Footer ---  */}
      <footer className="relative z-10 py-10 border-t border-white/5 text-center px-6 bg-[#050505]">
        <div className="flex flex-col items-center gap-2">
          <p className="text-slate-400 text-sm font-medium">
            Forensic Council is an academic research project.
          </p>
          <p className="text-slate-600 text-xs max-w-md">
            Results are generated by AI agents and may occasionally contain inaccuracies.
            Do not use findings as sole evidence in legal proceedings.
          </p>
        </div>
      </footer>

      {/* ===== GLASS UPLOAD MODAL ===== */}
      <AnimatePresence>
        {modalOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[200] flex items-center justify-center p-4"
            onClick={(e) => { if (e.target === e.currentTarget) { setModalOpen(false); handleClearFile(); } }}
          >
            {/* Backdrop */}
            <div className="absolute inset-0 bg-black/70 backdrop-blur-xl" />

            <motion.div
              initial={{ scale: 0.92, opacity: 0, y: 20 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.92, opacity: 0, y: 20 }}
              transition={{ type: "spring", stiffness: 300, damping: 25 }}
              className="relative w-full max-w-xl rounded-[2rem] overflow-hidden z-10
                bg-gradient-to-b from-white/[0.07] to-black/80
                border border-white/[0.12]
                shadow-[0_32px_80px_rgba(0,0,0,0.8),inset_0_1px_0_rgba(255,255,255,0.12)]
                backdrop-blur-3xl"
            >
              {/* Glass top shine */}
              <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/40 to-transparent" />
              <div className="absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-white/[0.04] to-transparent pointer-events-none" />

              {/* Header */}
              <div className="relative px-8 pt-8 pb-6 flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-3 mb-1">
                    <div className="w-8 h-8 rounded-lg bg-cyan-500/20 border border-cyan-500/30 flex items-center justify-center">
                      <UploadCloud className="w-4 h-4 text-cyan-400" />
                    </div>
                    <h2 className="text-xl font-bold text-white tracking-tight">Evidence Intake</h2>
                  </div>
                  <p className="text-slate-400 text-sm ml-11">Submit a digital artifact for council analysis</p>
                </div>
                <button
                  onClick={() => { setModalOpen(false); handleClearFile(); }}
                  className="p-2 text-slate-500 hover:text-white hover:bg-white/10 rounded-xl transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Body */}
              <div className="px-8 pb-8">
                <AnimatePresence mode="wait">
                  {!file ? (
                    /* ---- DROP ZONE ---- */
                    <motion.div
                      key="dropzone"
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -8 }}
                    >
                      <input
                        type="file"
                        ref={fileInputRef}
                        className="hidden"
                        accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.txt"
                        onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
                      />
                      <div
                        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                        onDragLeave={() => setIsDragging(false)}
                        onDrop={(e) => {
                          e.preventDefault();
                          setIsDragging(false);
                          if (e.dataTransfer.files?.[0]) handleFile(e.dataTransfer.files[0]);
                        }}
                        onClick={() => fileInputRef.current?.click()}
                        className={`
                          relative cursor-pointer rounded-2xl border-2 border-dashed
                          flex flex-col items-center justify-center
                          py-14 px-8 text-center
                          transition-all duration-300 group overflow-hidden
                          ${isDragging
                            ? "border-cyan-400/70 bg-cyan-500/[0.06]"
                            : "border-white/10 bg-white/[0.02] hover:border-cyan-500/40 hover:bg-cyan-500/[0.03]"
                          }
                        `}
                      >
                        {/* Animated radial glow when dragging */}
                        <motion.div
                          animate={{ opacity: isDragging ? 1 : 0 }}
                          className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(34,211,238,0.08),transparent_70%)] pointer-events-none"
                        />
                        {/* Upload graphic */}
                        <div className={`relative mb-6 transition-transform duration-300 ${isDragging ? "scale-110" : "group-hover:scale-105"}`}>
                          <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-cyan-500/15 to-blue-600/10 border border-cyan-500/20 flex items-center justify-center shadow-[0_0_30px_rgba(34,211,238,0.12)] relative">
                            {/* Orbiting ring */}
                            <div className="absolute inset-[-8px] rounded-[20px] border border-cyan-500/15 border-dashed animate-[spin_8s_linear_infinite]" />
                            <UploadCloud className={`w-9 h-9 transition-colors ${isDragging ? "text-cyan-300" : "text-cyan-500"}`} />
                          </div>
                          {/* Small corner icons */}
                          {[FileImage, FileAudio, FileVideo].map((Icon, i) => (
                            <div
                              key={i}
                              className="absolute w-7 h-7 rounded-lg bg-black/60 border border-white/10 flex items-center justify-center"
                              style={{
                                top: i === 0 ? "-10px" : i === 2 ? "auto" : "auto",
                                bottom: i === 2 ? "-10px" : "auto",
                                left: i === 2 ? "-12px" : "auto",
                                right: i === 0 ? "-12px" : i === 1 ? "-14px" : "auto",
                              }}
                            >
                              <Icon className="w-3.5 h-3.5 text-slate-400" />
                            </div>
                          ))}
                        </div>
                        <p className="text-white font-semibold text-base mb-1">
                          {isDragging ? "Drop to submit evidence" : "Drag & drop your file here"}
                        </p>
                        <p className="text-slate-500 text-sm mb-5">or click anywhere to browse</p>
                        <div className="flex gap-2 flex-wrap justify-center">
                          {["IMAGE", "VIDEO", "AUDIO", "PDF", "DOC"].map(t => (
                            <span key={t} className="px-2.5 py-1 bg-white/[0.04] border border-white/[0.08] rounded-full text-[10px] font-mono text-slate-500 tracking-wider">
                              {t}
                            </span>
                          ))}
                        </div>
                      </div>
                      {validationError && (
                        <p className="mt-4 text-red-400 text-sm text-center font-medium">{validationError}</p>
                      )}
                    </motion.div>
                  ) : (
                    /* ---- FILE PREVIEW ---- */
                    <motion.div
                      key="preview"
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -8 }}
                      className="flex flex-col gap-5"
                    >
                      {/* Preview area */}
                      <div className="w-full rounded-2xl overflow-hidden bg-black/40 border border-white/[0.08] relative" style={{ minHeight: "200px" }}>
                        {previewUrl && file?.type.startsWith("image/") && (
                          /* eslint-disable-next-line @next/next/no-img-element -- Dynamic blob URL preview, cannot use Next/Image */
                          <img
                            src={previewUrl}
                            alt="Evidence preview"
                            className="w-full max-h-64 object-contain"
                          />
                        )}
                        {previewUrl && file?.type.startsWith("video/") && (
                          <video
                            src={previewUrl}
                            className="w-full max-h-64 object-contain"
                            controls={false}
                            muted
                            autoPlay
                            loop
                            playsInline
                          />
                        )}
                        {!previewUrl && file && (
                          /* Non-previewable file — graphic placeholder */
                          <div className="flex flex-col items-center justify-center h-48 gap-4">
                            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-cyan-500/15 to-blue-600/10 border border-cyan-500/20 flex items-center justify-center shadow-[0_0_20px_rgba(34,211,238,0.15)]">
                              {file.type.startsWith("audio/")
                                ? <FileAudio className="w-8 h-8 text-cyan-400" />
                                : file.type === "application/pdf"
                                  ? <File className="w-8 h-8 text-rose-400" />
                                  : <File className="w-8 h-8 text-slate-400" />
                              }
                            </div>
                            {/* Waveform / document graphic */}
                            {file.type.startsWith("audio/") ? (
                              <div className="flex items-end gap-1 h-8">
                                {[3, 7, 5, 9, 6, 4, 8, 5, 7, 3, 6, 8, 4, 7, 5].map((h, i) => (
                                  <motion.div
                                    key={i}
                                    className="w-1 bg-cyan-500/60 rounded-full"
                                    animate={{ height: [`${h * 3}px`, `${(h * 3 + 10)}px`, `${h * 3}px`] }}
                                    transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.08, ease: "easeInOut" }}
                                  />
                                ))}
                              </div>
                            ) : (
                              <div className="flex flex-col gap-1.5 w-32 opacity-30">
                                {[100, 80, 90, 60].map((w, i) => (
                                  <div key={i} className="h-1.5 bg-slate-400 rounded-full" style={{ width: `${w}%` }} />
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                        {/* File name overlay at bottom */}
                        <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/80 to-transparent px-4 py-3">
                          <p className="text-xs font-mono text-slate-300 truncate">{file.name}</p>
                          <p className="text-[10px] text-slate-500 mt-0.5">{(file.size / 1024 / 1024).toFixed(2)} MB · {file.type || "unknown"}</p>
                        </div>
                      </div>

                      {/* Action buttons */}
                      <div className="flex gap-3">
                        {/* New Upload */}
                        <button
                          onClick={handleClearFile}
                          className="flex-1 flex items-center justify-center gap-2.5 px-5 py-3.5 rounded-xl
                            bg-white/[0.04] border border-white/[0.10]
                            text-slate-300 font-semibold text-sm
                            hover:bg-white/[0.08] hover:border-white/20 hover:text-white
                            transition-all duration-200
                            shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]"
                        >
                          <RotateCcw className="w-4 h-4 text-slate-400" />
                          New Upload
                        </button>
                        {/* Initiate Analysis */}
                        <button
                          onClick={handleInitiate}
                          className="flex-1 flex items-center justify-center gap-2.5 px-5 py-3.5 rounded-xl
                            bg-gradient-to-r from-emerald-500 to-cyan-500
                            text-white font-bold text-sm
                            hover:from-emerald-400 hover:to-cyan-400
                            hover:scale-[1.02] hover:shadow-[0_0_30px_rgba(16,185,129,0.4)]
                            transition-all duration-200
                            shadow-[0_4px_20px_rgba(16,185,129,0.25),inset_0_1px_0_rgba(255,255,255,0.2)]
                            border border-white/[0.15]"
                        >
                          Initiate Analysis
                          <ArrowRight className="w-4 h-4" />
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
