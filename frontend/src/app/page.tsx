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

/* ─── Forensic Shield Graphic (Minimalist) ─────────────────────────────── */
function ForensicShield() {
  return (
    <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-20" aria-hidden="true">
      <div className="relative w-[500px] h-[500px] flex items-center justify-center">
        <div className="absolute inset-0 rounded-full border border-indigo-500/20 shadow-[0_0_80px_rgba(99,102,241,0.05)]" />
        <ShieldCheck className="w-48 h-48 text-indigo-400/40" strokeWidth={1} />
        <div className="absolute w-[400px] h-[400px] rounded-full border border-dashed border-indigo-400/10 animate-[spin_60s_linear_infinite]" />
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
    <div className="relative inline-block">
      <button
        onClick={onOpen}
        disabled={phase !== "idle"}
        className="btn btn-primary px-8 py-4 rounded-full text-lg shadow-xl"
      >
        <span>
          {phase === "idle" || phase === "closing" ? "Begin Analysis" : "Opening…"}
        </span>
        <ArrowRight className="w-5 h-5" />
      </button>
    </div>
  );
}

/* ─── Glass card ─────────────────────────────────────────────────────────── */
interface GlassCardProps {
  children: ReactNode;
  className?: string;
  glowColor?: "cyan" | "violet" | "emerald";
}

function SurfaceCard({
  children,
  className = "",
}: GlassCardProps) {
  return (
    <div className={`surface-panel p-6 ${className}`}>
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
    <div className="relative min-h-screen bg-background text-foreground font-sans selection:bg-indigo-500/30">

      {/* Background System */}
      <div className="fixed inset-0 z-0 pointer-events-none overflow-hidden text-foreground">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_-20%,rgba(99,102,241,0.08),transparent_70%)]" />
      </div>

      {/* Skip-to-content link for keyboard users */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[9999]
          focus:px-4 focus:py-2 focus:bg-indigo-500 focus:text-white focus:rounded-lg focus:font-semibold focus:text-sm"
      >
        Skip to main content
      </a>

      <header className="fixed top-0 left-0 right-0 z-[60] px-6 h-16 flex items-center justify-between border-b border-border-subtle bg-background/80 backdrop-blur-md">
        <div className="flex items-center gap-3 cursor-pointer" onClick={() => router.push("/")}>
          <div className="w-8 h-8 bg-surface-high border border-border-bold rounded-lg flex items-center justify-center font-bold text-indigo-400 text-xs">
            FC
          </div>
          <span className="text-sm font-bold font-heading uppercase tracking-widest text-foreground/80">
            Forensic Council
          </span>
        </div>
      </header>

      <main id="main-content" className="relative z-10">

      {/* HERO */}
      <section
        aria-labelledby="hero-title"
        className="relative w-full min-h-screen flex flex-col items-center justify-center px-6 pt-16 z-10 overflow-hidden"
      >
        <ForensicShield />

        <div className="relative z-30 flex flex-col items-center text-center max-w-4xl mx-auto">

          {/* Headline */}
          <motion.h1
            id="hero-title"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="text-5xl sm:text-6xl md:text-7xl font-bold mb-6 tracking-tight leading-tight font-heading"
          >
            Forensic Evidence Analysis
          </motion.h1>

          {/* Sub */}
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2, duration: 0.6 }}
            className="text-foreground/60 text-lg sm:text-xl max-w-2xl mb-12 leading-relaxed"
          >
            Specialist AI agents independently examine your evidence — pixel integrity, audio authenticity,
            object detection, temporal analysis, and metadata provenance — for a synthesized forensic verdict.
          </motion.p>

          {/* CTA */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-6 relative z-10 w-full max-w-2xl px-4">
            <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.3 }} className="w-full sm:w-auto">
              <ActionBtn onOpen={handleCTAClick} phase={envPhase} />
            </motion.div>
          </div>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section aria-labelledby="process-title" className="relative z-10 py-32 px-6 border-t border-border-subtle">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-20">
            <p className="text-xs font-mono text-indigo-400 uppercase tracking-widest mb-3 font-bold">Process</p>
            <h2 id="process-title" className="text-4xl font-bold text-foreground">How It Works</h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 relative">
            {[
              { step: "01", title: "Evidence Intake",     desc: "Upload digital media artifacts — CCTV footage, photographs, audio recordings, or raw metadata exports." },
              { step: "02", title: "Agent Consultation",  desc: "Five specialist agents process the evidence stream concurrently and independently identifying anomalies." },
              { step: "03", title: "Arbiter Synthesis",   desc: "The Council Arbiter cross-references all findings, resolves contradictions, and computes confidence scores." },
              { step: "04", title: "Signed Verdict",      desc: "A cryptographically signed forensic report is generated with an authenticity verdict and chain-of-custody log." },
            ].map((item, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1, duration: 0.4 }}
                className="group"
              >
                <SurfaceCard className="h-full flex flex-col">
                  <div className="text-indigo-400 font-mono text-sm font-bold mb-4">{item.step}</div>
                  <h3 className="text-lg font-bold text-foreground mb-3">{item.title}</h3>
                  <p className="text-foreground/60 text-sm leading-relaxed">{item.desc}</p>
                </SurfaceCard>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* MEET THE COUNCIL */}
      <section aria-labelledby="council-title" className="relative z-10 py-32 px-6 border-t border-border-subtle">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <p className="text-xs font-mono text-indigo-400 uppercase tracking-widest mb-3 font-bold">Agents</p>
            <h2 id="council-title" className="text-4xl font-bold text-foreground">Meet the Multi-Agent Council</h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
            {AGENTS_DATA.map((agent, i) => (
              <motion.div
                key={agent.id}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.05, duration: 0.4 }}
              >
                <SurfaceCard className="h-full flex flex-col items-center text-center">
                  <div className="mb-6">
                    <AgentIcon agentId={agent.id} size="lg" className="text-indigo-400" />
                  </div>
                  <h3 className="text-sm font-bold text-foreground mb-1">{agent.name}</h3>
                  <p className="text-[11px] text-indigo-400/80 font-mono mb-3 uppercase tracking-wider">{agent.role}</p>
                  <p className="text-xs text-foreground/50 leading-relaxed">{agent.desc}</p>
                </SurfaceCard>
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
            className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-background/60 backdrop-blur-sm"
            onClick={(e) => { if (e.target === e.currentTarget) handleModalClose(); }}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="relative w-full max-w-lg z-10 surface-panel shadow-2xl overflow-hidden"
            >
              <div className="px-6 py-4 flex items-center justify-between border-b border-border-subtle bg-surface-mid">
                <h2 id="evidence-modal-title" className="text-sm font-bold text-foreground flex items-center gap-2">
                  <UploadCloud className="w-4 h-4 text-indigo-400" /> Evidence Intake
                </h2>
                <button onClick={handleModalClose} className="p-1 hover:bg-surface-high rounded-md transition-colors">
                  <X className="w-4 h-4 text-foreground/40" />
                </button>
              </div>

              <div className="p-6">
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
                      <div
                        role="button"
                        tabIndex={0}
                        onClick={() => fileInputRef.current?.click()}
                        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                        onDragLeave={() => setIsDragging(false)}
                        onDrop={(e) => { e.preventDefault(); setIsDragging(false); e.dataTransfer.files?.[0] && handleFile(e.dataTransfer.files[0]); }}
                        className={`h-48 border-2 border-dashed rounded-xl flex flex-col items-center justify-center transition-colors
                          ${isDragging ? "border-indigo-500 bg-indigo-500/5" : "border-border-bold bg-surface-low hover:border-indigo-500/50 hover:bg-surface-mid"}`}
                      >
                        <UploadCloud className="w-8 h-8 text-indigo-400/50 mb-3" />
                        <p className="text-sm font-medium text-foreground">Click to upload or drag and drop</p>
                        <p className="text-xs text-foreground/40 mt-1">Images, Video, or Audio (max 50MB)</p>
                      </div>
                      {validationError && (
                        <p className="mt-3 text-red-400 text-xs text-center font-medium">{validationError}</p>
                      )}
                    </motion.div>
                  ) : (
                    <motion.div key="preview" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
                      <div className="aspect-video rounded-lg overflow-hidden bg-surface-low border border-border-subtle relative flex items-center justify-center">
                        {previewUrl && file.type.startsWith("image/") ? (
                          <img src={previewUrl} alt="Preview" className="w-full h-full object-contain" />
                        ) : previewUrl && file.type.startsWith("video/") ? (
                          <video src={previewUrl} className="w-full h-full object-contain" muted autoPlay loop />
                        ) : (
                          <div className="flex flex-col items-center text-foreground/40">
                            <File className="w-12 h-12 mb-2" />
                            <span className="text-xs font-mono lowercase">{file.name}</span>
                          </div>
                        )}
                        <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent pointer-events-none" />
                        <div className="absolute bottom-3 left-4 right-4 flex items-center justify-between">
                          <span className="text-[10px] font-bold text-white/80 uppercase tracking-widest">{file.type.split("/")[1]} • {(file.size/1024/1024).toFixed(2)}MB</span>
                          <ShieldCheck className="w-4 h-4 text-emerald-400" />
                        </div>
                      </div>

                      <div className="flex gap-2">
                        <button onClick={handleClearFile} className="btn btn-secondary flex-1">Clear</button>
                        <button onClick={handleInitiate} className="btn btn-primary flex-1">
                          {isTransitioning ? "Preparing..." : "Initiate Analysis"}
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
