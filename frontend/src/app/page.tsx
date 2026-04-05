"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowRight,
} from "lucide-react";

import { autoLoginAsInvestigator } from "@/lib/api";
import { __pendingFileStore } from "@/lib/pendingFileStore";
import { AGENTS, HOW_IT_WORKS } from "@/lib/constants";

import { UploadModal } from "@/components/evidence/UploadModal";
import { UploadSuccessModal } from "@/components/evidence/UploadSuccessModal";

// ── Framer Motion Variants ────────────────────────────────────────────────────
const cardHover = {
  rest: { scale: 1, boxShadow: "0 0 0px rgba(34,211,238,0)" },
  hover: {
    scale: 1.02,
    boxShadow: "0 0 20px rgba(34,211,238,0.1)",
    borderColor: "rgba(34, 211, 238, 0.25)",
    transition: { duration: 0.3, ease: "easeOut" as const },
  },
};

export default function Home() {
  const router = useRouter();
  const [showUpload, setShowUpload] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isAuthenticating, setIsAuthenticating] = useState(false);

  useEffect(() => {
    const resetHome = () => {
      setShowUpload(false);
      setSelectedFile(null);
      setIsAuthenticating(false);
    };

    window.addEventListener("fc:reset-home", resetHome);
    return () => window.removeEventListener("fc:reset-home", resetHome);
  }, []);

  const handleStartAnalysis = useCallback(async () => {
    if (!selectedFile) return;

    setIsAuthenticating(true);
    try {
      await autoLoginAsInvestigator();
      // Signal to the evidence page that the session cookie is already live so it
      // can skip a redundant auth round-trip before starting the investigation.
      // (access_token is httpOnly — JS on the evidence page cannot see it directly.)
      sessionStorage.setItem("forensic_auth_ok", "1");
    } catch (err) {
      console.error("Auto-login failed:", err);
      // Continue — the evidence page will retry auth before starting the investigation.
    } finally {
      setIsAuthenticating(false);
    }

    __pendingFileStore.file = selectedFile;
    sessionStorage.setItem("forensic_auto_start", "true");
    sessionStorage.setItem("fc_show_loading", "true");
    router.push("/evidence", { scroll: true });
  }, [router, selectedFile]);

  return (
    <main className="min-h-screen selection:bg-cyan-500/30 selection:text-cyan-200" id="main-content">
      {/* ── Hero Section ────────────────────────────────────────────────────── */}
      <section id="hero" className="relative pt-48 pb-24 overflow-hidden min-h-[85vh] flex items-center">
        {/* Background elements */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-7xl aspect-square bg-[radial-gradient(circle_at_50%_0%,rgba(34,211,238,0.08)_0%,transparent_70%)] pointer-events-none" />
        <div className="absolute top-1/4 left-0 w-96 h-96 bg-indigo-500/5 blur-[120px] rounded-full pointer-events-none" />
        <div className="absolute bottom-0 right-0 w-[500px] h-[500px] bg-cyan-500/5 blur-[150px] rounded-full pointer-events-none" />

        <div className="max-w-7xl mx-auto px-6 relative z-10 w-full">
          <div className="max-w-4xl mx-auto text-center">
            <motion.div
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, ease: "easeOut" }}
            >
              <h1 className="text-5xl md:text-7xl font-black text-white mb-10 leading-[1.1] tracking-tight flex flex-col items-center">
                <span className="whitespace-nowrap">Multi Agent Forensic</span>
                <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 via-indigo-400 to-cyan-400 bg-[length:200%_auto] animate-gradient-x whitespace-nowrap">
                  Evidence Analysis System
                </span>
              </h1>
              
              <p className="text-xl md:text-2xl text-white/90 leading-relaxed mb-16 max-w-4xl mx-auto drop-shadow-sm">
                An advanced forensic intelligence platform where specialized AI agents 
                collaborate to authenticate digital evidence, perform deep-fake 
                detection, and generate cryptographically signed verdicts.
              </p>

              <div className="flex justify-center">
                <button
                  type="button"
                  onClick={() => setShowUpload(true)}
                  className="btn-pill-primary px-12 py-5 text-lg font-bold group shadow-[0_20px_50px_rgba(8,145,178,0.2)] hover:shadow-[0_20px_60px_rgba(8,145,178,0.4)] transition-all flex items-center gap-3"
                >
                  {isAuthenticating ? "Initialising..." : "Start Analysis"}
                  <ArrowRight className="w-6 h-6 group-hover:translate-x-2 transition-transform" />
                </button>
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      {/* ── How It Works Section ─────────────────────────────────────────── */}
      <section id="technology" className="py-24 relative">
        <div className="max-w-7xl mx-auto px-6 relative z-10">
          <div className="text-center mb-16">
            <h2 className="text-4xl md:text-5xl font-black text-white mb-6">
              How <span className="text-cyan-400">Forensic Council</span> Works
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
            {HOW_IT_WORKS.map((item, i) => (
              <motion.div
                key={item.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: 0.1 * i }}
                whileHover="hover"
                variants={cardHover}
                className="p-8 rounded-[2.5rem] border border-white/5 glass-panel group relative overflow-hidden"
              >
                <div
                  className="absolute -top-12 -right-12 w-24 h-24 blur-3xl opacity-0 group-hover:opacity-100 transition-opacity"
                  style={{ background: item.color }}
                />
                <div className="relative z-10 flex flex-col items-center text-center">
                  <div
                    className="w-14 h-14 rounded-2xl flex items-center justify-center mb-8 border"
                    style={{
                      background: `rgba(${item.rgb}, 0.1)`,
                      borderColor: `rgba(${item.rgb}, 0.2)`,
                    }}
                  >
                    <item.icon
                      className="w-7 h-7"
                      style={{ color: item.color }}
                    />
                  </div>
                  <p className="text-[10px] font-mono font-bold tracking-widest text-white/30 uppercase mb-3">
                    {item.tag}
                  </p>
                  <h3 className="text-xl font-bold text-white mb-4">
                    {item.title}
                  </h3>
                  <p className="text-sm text-white/40 leading-relaxed max-w-[280px]">
                    {item.desc}
                  </p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>
      <section id="agents" className="py-24 bg-surface-low/30">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-4xl md:text-5xl font-bold text-white mb-6">
              Meet the Council of Agents
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {AGENTS.map((agent, i) => (
              <motion.div
                key={agent.id}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: i * 0.05 }}
                className="p-8 rounded-[2.5rem] bg-white/[0.02] border border-white/[0.05] hover:bg-white/[0.04] transition-all group"
              >
                <div className="flex flex-col items-center text-center">
                  <div className="flex items-center justify-center mb-4 relative">
                    <div
                      className="w-16 h-16 rounded-2xl flex items-center justify-center border"
                      style={{
                        background: `rgba(${agent.bgRgb}, 0.15)`,
                        borderColor: `rgba(${agent.bgRgb}, 0.3)`,
                      }}
                    >
                      <agent.icon
                        className="w-8 h-8"
                        style={{ color: agent.color }}
                      />
                    </div>
                  </div>
                  <div className="inline-flex items-center px-4 py-1.5 rounded-full bg-white/5 border border-white/5 text-[10px] font-bold text-white/40 uppercase tracking-widest mb-3">
                    {agent.badge}
                  </div>
                  <h3 className="text-2xl font-bold text-white mb-3">
                    {agent.name}
                  </h3>
                  <p className="text-white/40 text-sm leading-relaxed max-w-[260px]">
                    {agent.desc}
                  </p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Modals ──────────────────────────────────────────────────────────── */}
      <AnimatePresence>
        {showUpload && !selectedFile && (
          <UploadModal
            onClose={() => setShowUpload(false)}
            onFileSelected={(f) => {
              setSelectedFile(f);
            }}
          />
        )}
        {selectedFile && (
          <UploadSuccessModal
            file={selectedFile}
            onNewUpload={() => setSelectedFile(null)}
            onStartAnalysis={handleStartAnalysis}
          />
        )}
      </AnimatePresence>
    </main>
  );
}
