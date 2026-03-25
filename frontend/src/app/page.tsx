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

/* ─── Precomputed particle data (avoids Math.random() in render) ─────────── */
const PARTICLE_DATA = [...Array(12)].map(() => ({
  x: (Math.random() - 0.5) * 1200,
  y: (Math.random() - 0.5) * 800,
  duration: Math.random() * 10 + 10,
  delay: Math.random() * 5,
  showLine: Math.random() > 0.5,
}));

/* ─── Microscope Scanner Animation ───────────────────────────────────── */
function MicroscopeScanner() {
  return (
    <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-0 overflow-hidden" aria-hidden="true">
      {/* Background Glows - Refined Amber/Gold */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[1000px] h-[1000px] bg-amber-600/5 blur-[150px] rounded-full animate-pulse" />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-amber-500/5 blur-[120px] rounded-full delay-1000 animate-pulse" />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-white/5 blur-[100px] rounded-full delay-2000" />

      <div className="relative w-full max-w-5xl h-[700px] flex items-center justify-center">
        
        {/* Evidence Document Mockup - Enhanced Materiality */}
        <motion.div 
          initial={{ opacity: 0, scale: 0.9, y: 20 }}
          animate={{ opacity: 0.6, scale: 1, y: 0 }}
          transition={{ duration: 1.5, ease: "easeOut" }}
          className="relative w-80 h-[450px] bg-white/[0.02] border border-white/10 rounded-lg shadow-[0_0_50px_rgba(0,0,0,0.5)] overflow-hidden backdrop-blur-md"
        >
             {/* Micro-grid Pattern */}
             <div className="absolute inset-0 opacity-[0.03]" 
                  style={{ backgroundImage: 'radial-gradient(circle, white 1px, transparent 1px)', backgroundSize: '16px 16px' }} />

             {/* Content Mockup */}
             <div className="p-10 space-y-6">
               <div className="h-1.5 bg-amber-400/20 w-1/2 rounded-full" />
               <div className="space-y-4">
                 {[...Array(8)].map((_, i) => (
                   <div key={i} className="h-0.5 bg-white/5 w-full rounded-full" />
                 ))}
               </div>
               <div className="h-32 bg-amber-500/5 w-full rounded-xl border border-white/5 relative overflow-hidden group">
                  <div className="absolute inset-0 flex items-center justify-center">
                    <Fingerprint className="w-20 h-20 text-amber-400/10 transition-transform duration-700 group-hover:scale-110" strokeWidth={0.5} />
                  </div>
                  {/* Internal Scanning Detail */}
                  <motion.div 
                    animate={{ left: ["-100%", "200%"] }}
                    transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
                    className="absolute top-0 bottom-0 w-20 bg-gradient-to-r from-transparent via-amber-500/10 to-transparent skew-x-12"
                  />
               </div>
               <div className="space-y-4">
                 {[...Array(6)].map((_, i) => (
                   <div key={i} className="h-0.5 bg-white/5 w-full rounded-full" />
                 ))}
               </div>
             </div>

             {/* Scanning Line - Precision Laser Style */}
             <motion.div 
                animate={{ top: ["-5%", "105%", "-5%"] }}
                transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}
                className="absolute left-0 right-0 h-px bg-amber-400 shadow-[0_0_15px_rgba(217,119,6,0.8)] z-10"
             >
                <div className="absolute right-0 top-1/2 -translate-y-1/2 w-24 h-[1px] bg-gradient-to-l from-amber-400 to-transparent opacity-50" />
                <div className="absolute left-0 top-1/2 -translate-y-1/2 w-24 h-[1px] bg-gradient-to-r from-amber-400 to-transparent opacity-50" />
             </motion.div>

             {/* Tech Readout */}
             <div className="absolute bottom-4 left-6 right-6 flex justify-between items-end text-[7px] font-mono text-amber-400/40 uppercase tracking-[0.2em]">
                <div>
                  ID: PX-8821 <br />
                  AUTH: CERTIFIED
                </div>
                <div className="text-right">
                  LAYER: MICROSCOPIC <br />
                  SENS: ULTRA-HIGH
                </div>
             </div>
        </motion.div>

        {/* Microscope Lens / Scanning Circle - More complex mechanical look */}
        <motion.div 
          animate={{ 
            x: [-150, 150, -150], 
            y: [-100, 100, -100],
            rotate: [0, 360]
          }}
          transition={{ 
            x: { duration: 20, repeat: Infinity, ease: "easeInOut" },
            y: { duration: 15, repeat: Infinity, ease: "easeInOut" },
            rotate: { duration: 60, repeat: Infinity, ease: "linear" }
          }}
          className="absolute w-64 h-64 rounded-full border border-amber-500/20 bg-amber-500/5 backdrop-blur-[8px] shadow-[0_0_100px_rgba(217,119,6,0.1)] flex items-center justify-center z-20 overflow-hidden"
        >
          {/* Inner Mechanics */}
          <div className="absolute inset-0 rounded-full border border-white/5 animate-[spin_40s_linear_infinite]" />
          <div className="absolute inset-[10%] rounded-full border border-teal-500/10 animate-[spin_25s_linear_infinite_reverse]" />
          
          {/* Crosshair Details */}
          <div className="absolute inset-0 flex items-center justify-center opacity-30">
            <div className="w-full h-px bg-white/10" />
            <div className="h-full w-px bg-white/10" />
          </div>

          {/* Compass Marks */}
          {[...Array(12)].map((_, i) => (
            <div 
              key={i} 
              className="absolute w-1 h-3 bg-white/10" 
              style={{ transform: `rotate(${i * 30}deg) translateY(-110px)` }} 
            />
          ))}
          
          <Scan className="w-20 h-20 text-indigo-400/40" strokeWidth={0.5} />
          
          {/* Scanning Sweeps */}
          <motion.div 
            animate={{ opacity: [0, 0.5, 0] }}
            transition={{ duration: 2, repeat: Infinity }}
            className="absolute inset-0 bg-gradient-to-tr from-transparent via-indigo-500/5 to-transparent"
          />
        </motion.div>

        {/* Floating Particles / Data Fragments */}
        {PARTICLE_DATA.map((p, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0 }}
            animate={{
              opacity: [0, 0.4, 0],
              scale: [0.5, 1.2, 0.5],
              x: p.x,
              y: p.y,
            }}
            transition={{ duration: p.duration, repeat: Infinity, delay: p.delay }}
            className="absolute"
          >
            <div className="w-1 h-1 bg-amber-400/30 rounded-full blur-[1px]" />
            {p.showLine && <div className="mt-2 w-8 h-[1px] bg-amber-400/10" />}
          </motion.div>
        ))}

      </div>
    </div>
  );
}


/* ─── Envelope CTA Animation ─────────────────────────────────────────────── */
type EnvelopePhase = "idle" | "opening" | "open" | "closing";

function ActionBtn({
  onOpen,
  phase,
}: {
  onOpen: () => void;
  phase: EnvelopePhase;
}) {
  return (
    <div className="relative inline-block group">
      <button
        onClick={onOpen}
        disabled={phase !== "idle"}
        className={`btn-premium-amber shadow-lg transition-all
          ${(phase !== "idle" && phase !== "closing") ? "opacity-50 grayscale pointer-events-none" : ""}`}
      >
        <span className="relative z-10">
          {phase === "idle" || phase === "closing" ? "Begin Forensic Analysis" : "Initializing Systems…"}
        </span>
        <ArrowRight className={`w-5 h-5 transition-transform duration-300 ${phase === "idle" ? "group-hover:translate-x-1" : ""}`} />
      </button>
      
      {/* Decorative Outer Glow */}
      <div className="absolute inset-0 -z-10 bg-teal-500/20 blur-2xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
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
    setTimeout(() => {
      setEnvPhase("open");
      setModalOpen(true);
    }, 500);
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
    const investigatorId =
      storedId && validIdPattern.test(storedId)
        ? storedId
        : "REQ-" + (Math.floor(Math.random() * 900000) + 100000);

    sessionStorage.setItem("forensic_pending_file_name", file.name);
    sessionStorage.setItem("forensic_case_id", caseId);
    sessionStorage.setItem("forensic_investigator_id", investigatorId);
    sessionStorage.setItem("forensic_auto_start", "true");
    (window as any).__forensic_pending_file = file;

    (window as any).__forensic_investigation_promise = startInvestigation(
      file,
      caseId,
      investigatorId
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

  if (!isMounted) return <div className="min-h-screen bg-[#0a0a0b]" />;

  return (
    <div className="relative min-h-screen bg-background text-foreground font-sans selection:bg-teal-500/30">

      {/* Background System */}
      <div className="fixed inset-0 z-0 pointer-events-none overflow-hidden" aria-hidden="true">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_-20%,rgba(217,119,6,0.05),transparent_70%)]" />
      </div>

      <a href="#main-content" className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[9999] focus:px-4 focus:py-2 focus:bg-amber-600 focus:text-black focus:rounded focus:font-bold">
        Skip to main content
      </a>

      <header className="fixed top-0 left-0 right-0 z-[60] px-8 h-20 flex items-center justify-between bg-background/60 backdrop-blur-2xl border-b border-white/5">
        <div 
          className="flex items-center gap-4 cursor-pointer group" 
          onClick={() => router.push("/")}
          role="button"
          aria-label="Forensic Council Home"
          tabIndex={0}
          onKeyDown={(e) => e.key === "Enter" && router.push("/")}
        >
          <div className="w-10 h-10 liquid-glass flex items-center justify-center font-bold text-amber-500 text-sm group-hover:border-amber-400/50 transition-all duration-300">
            FC
          </div>
          <span className="text-sm font-black uppercase tracking-[0.4em] text-foreground/90 group-hover:text-amber-400 transition-colors">
            Forensic Council
          </span>
        </div>
      </header>

      <main id="main-content" className="relative z-10">

        {/* HERO */}
        <section aria-labelledby="hero-title" className="relative w-full min-h-screen flex flex-col items-center justify-center px-6 pt-24 overflow-hidden">
          <MicroscopeScanner />

          <div className="relative z-30 flex flex-col items-center text-center max-w-5xl mx-auto py-12">
            <motion.div
              initial={{ opacity: 0, y: -20 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-10 px-6 py-2 rounded bg-amber-500/5 border border-amber-500/10 text-amber-500 shadow-[0_0_20px_rgba(217,119,6,0.1)]"
            >
              <span className="text-[10px] font-bold uppercase tracking-[0.6em]">Advanced Forensic Intelligence</span>
            </motion.div>

            <motion.h1
              id="hero-title"
              initial={{ opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 1, ease: "easeOut" }}
              className="text-6xl sm:text-7xl md:text-9xl font-black mb-12 tracking-tighter leading-[0.85] text-white"
            >
              Multi-Agent <br />
              <span className="text-gradient-amber">Forensic Analysis</span>
            </motion.h1>

            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 0.7 }}
              transition={{ delay: 0.4, duration: 1 }}
              className="text-white text-lg sm:text-xl max-w-2xl mb-16 font-medium leading-relaxed px-4 balance"
            >
              Autonomous specialist agents independently audit digital evidence, resolve artifacts, and synthesize objective forensic verdicts with cryptographic certainty.
            </motion.p>

            <motion.div 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.6 }}
              className="relative z-10"
            >
              <ActionBtn onOpen={handleCTAClick} phase={envPhase} />
            </motion.div>
          </div>
        </section>

        {/* HOW IT WORKS */}
        <section aria-labelledby="process-title" className="relative z-10 py-40 px-6 border-t border-white/5 bg-surface-low">
          <div className="max-w-7xl mx-auto">
            <div className="text-center mb-24">
              <motion.div 
                initial={{ opacity: 0 }}
                whileInView={{ opacity: 1 }}
                viewport={{ once: true }}
                className="inline-flex items-center gap-4 mb-6"
              >
                <div className="w-12 h-px bg-amber-500/30" />
                <span className="text-xs font-mono text-amber-500/60 uppercase tracking-[0.6em] font-bold">The Protocol</span>
                <div className="w-12 h-px bg-amber-500/30" />
              </motion.div>
              <h2 id="process-title" className="text-5xl md:text-7xl font-black text-white mb-8 tracking-tight uppercase">System Workflow</h2>
              <p className="max-w-3xl mx-auto text-white/40 text-lg leading-relaxed text-center balance italic font-heading">
                "Autonomous precision through decentralized specialist intelligence."
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
              {[
                { step: "01", title: "Evidence Intake",     desc: "Upload digital media artifacts including CCTV footage, high-resolution photographs, or raw forensic metadata exports.", icon: <UploadCloud className="w-7 h-7" /> },
                { step: "02", title: "Agent Consultation",  desc: "Five specialist agents process the evidence stream concurrently, independently identifying anomalies and patterns.", icon: <Globe className="w-7 h-7" /> },
                { step: "03", title: "Arbiter Synthesis",   desc: "The Council Arbiter cross-references all findings, resolves contradictions, and computes confidence scores.", icon: <Scale className="w-7 h-7" /> },
                { step: "04", title: "Signed Verdict",      desc: "A cryptographically signed forensic report is generated, providing a comprehensive and immutable authenticity log.", icon: <ShieldCheck className="w-7 h-7" /> },
              ].map((item, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 30 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.1 }}
                  className="surface-panel-low h-full flex flex-col items-center p-10 text-center group cursor-pointer"
                >
                  <div className="mb-10 w-20 h-20 rounded-3xl bg-amber-500/5 flex items-center justify-center text-amber-400 border border-amber-500/20 group-hover:scale-110 group-hover:rotate-3 transition-all duration-500">
                    {item.icon}
                  </div>
                  <div className="mb-8">
                    <span className="text-[10px] font-mono text-amber-400/60 font-bold tracking-[0.4em] uppercase">PHASE {item.step}</span>
                    <h3 className="text-2xl font-bold text-white mt-3 tracking-tight">{item.title}</h3>
                  </div>
                  <p className="text-white/40 text-sm leading-relaxed text-justify hyphens-auto">{item.desc}</p>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* MEET THE COUNCIL */}
        <section className="py-40 px-6 relative overflow-hidden bg-background">
          <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-amber-500/20 to-transparent" />
          
          <div className="max-w-7xl mx-auto">
            <div className="mb-24 flex flex-col items-center">
              <span className="text-[10px] font-mono text-amber-500/40 uppercase tracking-[0.8em] font-bold mb-6">Autonomous Council</span>
              <h2 className="text-5xl md:text-8xl font-black text-white text-center leading-[0.9] tracking-tighter uppercase">Me<span className="text-gradient-amber">et the Agents</span></h2>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
              {AGENTS_DATA.map((agent, i) => (
                <motion.div 
                  key={agent.id}
                  initial={{ opacity: 0, y: 40 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.1 }}
                  whileHover={{ y: -8 }}
                  className="surface-panel-high border-white/5 p-10 relative group overflow-hidden rounded-none border-l-2 border-l-amber-500/20 hover:border-l-amber-500 transition-all duration-500"
                >
                  <div className="absolute top-0 right-0 p-4 font-mono text-[10px] text-white/10 group-hover:text-amber-500/20">
                    #{agent.id.toUpperCase()}
                  </div>
                  <div className="w-16 h-16 mb-10 rounded bg-amber-500/5 border border-amber-500/10 flex items-center justify-center group-hover:bg-amber-500/10 group-hover:scale-110 transition-all duration-500">
                    <AgentIcon agentId={agent.id} size="lg" className="text-amber-500/40 group-hover:text-amber-500 transition-colors" />
                  </div>
                  <h3 className="text-2xl font-bold text-white mb-4 tracking-tight group-hover:text-amber-400 transition-colors">{agent.name}</h3>
                  <p className="text-white/30 text-sm leading-relaxed mb-10">
                    {agent.desc}
                  </p>
                  <div className="flex items-center gap-2 text-[10px] font-mono text-amber-500/40 font-bold uppercase tracking-widest">
                    <div className="w-2 h-2 rounded-full bg-amber-500/20 animate-pulse" />
                    Unit Active
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

      </main>

      <GlobalFooter />

      {/* UPLOAD MODAL */}
      <AnimatePresence>
        {modalOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm"
            onClick={(e) => { if (e.target === e.currentTarget) handleModalClose(); }}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0, y: 20 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.9, opacity: 0, y: 20 }}
              className="relative w-full max-w-lg z-10 liquid-glass shadow-2xl overflow-hidden border-white/10"
            >
              <div className="flex items-center justify-between p-8 border-b border-white/5 bg-surface-mid">
                <div>
                  <h2 className="text-2xl font-black text-white uppercase tracking-tighter">Evidence Intake</h2>
                  <p className="text-[10px] font-mono text-amber-500/40 uppercase tracking-[0.4em] mt-1">System Phase 01: Secure Input</p>
                </div>
                <button onClick={handleModalClose} className="p-2 hover:bg-white/10 rounded-full transition-colors cursor-pointer">
                  <X className="w-5 h-5 text-white/40 hover:text-white" />
                </button>
              </div>

              <div className="p-8">
                <AnimatePresence mode="wait">
                  {!file ? (
                    <motion.div key="dz" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
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
                        onDrop={(e) => { e.preventDefault(); setIsDragging(false); const f = e.dataTransfer.files?.[0]; if (f) handleFile(f); }}
                        className={`w-full h-56 border-2 border-dashed rounded flex flex-col items-center justify-center transition-all cursor-pointer
                          ${isDragging ? "border-amber-400 bg-amber-400/5" : "border-white/5 bg-white/2 hover:border-amber-500/50 hover:bg-white/5"}`}
                        aria-label="Upload evidence file"
                      >
                        <UploadCloud className="w-10 h-10 text-amber-500/20 mb-4 group-hover:text-amber-500/50 transition-colors" aria-hidden="true" />
                        <p className="text-base font-bold text-white tracking-tight">Click to upload or drag artifacts</p>
                        <p className="text-[10px] text-white/30 mt-2 font-mono uppercase tracking-[0.2em]">Support: Image, Video, Audio (50MB)</p>
                      </button>
                      {validationError && (
                        <p className="mt-4 text-rose-400 text-xs text-center font-bold tracking-tight">{validationError}</p>
                      )}
                    </motion.div>
                  ) : (
                    <motion.div key="preview" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
                      <div className="aspect-video rounded-2xl overflow-hidden bg-black/40 border border-white/10 relative flex items-center justify-center shadow-inner">
                        {previewUrl && file!.type.startsWith("image/") ? (
                          <img src={previewUrl} alt="Preview" className="w-full h-full object-contain" />
                        ) : previewUrl && file!.type.startsWith("video/") ? (
                          <video src={previewUrl} className="w-full h-full object-contain" muted autoPlay loop />
                        ) : (
                          <div className="flex flex-col items-center text-white/20">
                            <File className="w-16 h-16 mb-4" />
                            <span className="text-xs font-mono uppercase tracking-widest">{file?.name}</span>
                          </div>
                        )}
                        <div className="absolute inset-0 bg-gradient-to-t from-black/80 to-transparent pointer-events-none" />
                        <div className="absolute bottom-4 left-6 right-6 flex items-center justify-between">
                          <span className="text-[10px] font-black text-white/90 uppercase tracking-[0.2em]">{file?.type.split("/")[1]} • {((file?.size ?? 0) / 1024 / 1024).toFixed(2)}MB</span>
                          <ShieldCheck className="w-5 h-5 text-amber-500 shadow-[0_0_10px_rgba(217,119,6,0.5)]" />
                        </div>
                      </div>

                      <div className="flex gap-4">
                        <button onClick={handleClearFile} className="btn-premium-glass flex-1 py-4 justify-center">Discard</button>
                        <button onClick={handleInitiate} className="btn-premium-amber flex-1 py-4 justify-center">
                          {isTransitioning ? "Sealing Evidence..." : "Initiate Audit"}
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
