"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, Shield, ShieldCheck, Activity, Cpu } from "lucide-react";

import { autoLoginAsInvestigator } from "@/lib/api";
import { __pendingFileStore } from "@/lib/pendingFileStore";
import { AGENTS, HOW_IT_WORKS } from "@/lib/constants";

import { UploadModal } from "@/components/evidence/UploadModal";
import { UploadSuccessModal } from "@/components/evidence/UploadSuccessModal";
import { Badge } from "@/components/ui/Badge";
import { StaggerIn, StaggerChild } from "@/components/ui/PageTransition";

import { MicroscopeScanner } from "@/components/ui/MicroscopeScanner";
import { ForensicGrid } from "@/components/ui/ForensicGrid";
import { SystemStatusHUD } from "@/components/ui/SystemStatusHUD";

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
      sessionStorage.setItem("forensic_auth_ok", "1");
    } catch (err) {
      console.error("Auto-login failed:", err);
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
      <MicroscopeScanner />

      {/* ── Hero Section ────────────────────────────────────────────────────── */}
      <section id="hero" className="relative h-screen overflow-hidden flex items-center justify-center bg-[#06090f] pt-24">
        <ForensicGrid />
        <SystemStatusHUD />
        
        {/* Deep Field Ambience */}
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(34,211,238,0.08)_0%,transparent_70%)] pointer-events-none" />
        <div className="absolute top-1/4 -left-20 w-[600px] h-[600px] bg-indigo-500/5 blur-[120px] rounded-full pointer-events-none animate-pulse" />
        <div className="absolute bottom-0 -right-20 w-[800px] h-[800px] bg-cyan-500/5 blur-[150px] rounded-full pointer-events-none transition-all duration-1000" />

        <div className="max-w-7xl mx-auto px-6 relative z-10 w-full">
          <div className="max-w-4xl mx-auto text-center">
            <StaggerIn>
              <StaggerChild>
                <h1 className="text-6xl md:text-9xl font-black text-white mb-12 leading-[0.9] tracking-tighter flex flex-col items-center">
                  <span className="opacity-40 text-[11px] font-mono tracking-[0.8em] mb-6 text-cyan-400 uppercase">Forensic OS // Neural Core v2.0.26</span>
                  <div className="flex flex-col items-center max-w-[90vw] mx-auto text-center px-4">
                    <span className="opacity-95 hover:text-glow transition-all duration-700 cursor-default">
                      Multi Agent Forensic
                    </span>
                    <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 via-white to-indigo-400 bg-[length:200%_auto] animate-gradient-x py-2 block">
                      Evidence Analysis System
                    </span>
                  </div>
                </h1>
              </StaggerChild>
              
              <StaggerChild>
                <p className="text-lg md:text-xl text-white/30 leading-relaxed mb-20 max-w-4xl mx-auto font-medium text-balance tracking-tight">
                  Utilizing a decentralized network of specialized neural units to dissect digital evidence with surgical precision. 
                  Each finding is cross-validated by an <span className="text-white/60">autonomous arbiter</span>, synthesizing complex forensic 
                  artifacts into a court-defensible, cohesive verdict.
                </p>
              </StaggerChild>

              <StaggerChild>
                <div className="flex justify-center">
                  <button
                    type="button"
                    onClick={() => setShowUpload(true)}
                    disabled={isAuthenticating}
                    className="group relative px-20 py-8 overflow-hidden transition-all duration-700 hover:scale-[1.02]"
                  >
                    {/* Animated Kinetic Background */}
                    <div className="absolute inset-0 bg-white group-hover:bg-cyan-50/90 transition-all duration-500" />
                    <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-1000 bg-[radial-gradient(circle_at_50%_50%,rgba(34,211,238,0.15)_0%,transparent_100%)]" />
                    
                    {/* Kinetic Shimmer Effect */}
                    <motion.div 
                      className="absolute inset-0 w-[200%] h-full bg-gradient-to-r from-transparent via-cyan-400/30 to-transparent -skew-x-12"
                      animate={{ x: ["-100%", "200%"] }}
                      transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
                    />

                    {/* Technical Borders */}
                    <div className="absolute inset-0 border border-black/[0.03]" />
                    <div className="absolute inset-0 m-[3px] border border-black/[0.03]" />
                    
                    {/* Corner HUD Accents */}
                    <div className="absolute top-0 left-0 w-3 h-3 border-t-2 border-l-2 border-black/10 group-hover:border-cyan-500/40 transition-colors" />
                    <div className="absolute bottom-0 right-0 w-3 h-3 border-b-2 border-r-2 border-black/10 group-hover:border-cyan-500/40 transition-colors" />

                    <div className="relative flex items-center justify-between gap-12 text-black">
                      <div className="flex flex-col items-start gap-1">
                        <span className="text-[11px] font-black uppercase tracking-[0.5em] leading-none">
                          {isAuthenticating ? "Initialising Protocol..." : "Begin Deep Analysis"}
                        </span>
                        <div className="flex items-center gap-2 opacity-30 group-hover:opacity-60 transition-opacity">
                           <div className="w-1.5 h-1.5 rounded-full bg-black animate-pulse" />
                           <span className="text-[6px] font-mono uppercase tracking-[0.3em]">SECURE_AUTH_REQUIRED</span>
                        </div>
                      </div>

                      {!isAuthenticating && (
                         <div className="w-8 h-8 flex items-center justify-center border border-black/10 rounded-full group-hover:border-cyan-500/20 transition-all overflow-hidden relative">
                            <motion.div
                              animate={{ x: [0, 20], opacity: [1, 0] }}
                              transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
                              className="absolute"
                            >
                               <ArrowRight className="w-4 h-4" />
                            </motion.div>
                            <motion.div
                              initial={{ x: -20, opacity: 0 }}
                              animate={{ x: [ -20, 0], opacity: [0, 1] }}
                              transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
                              className="absolute"
                            >
                               <ArrowRight className="w-4 h-4" />
                            </motion.div>
                         </div>
                      )}
                    </div>
                  </button>
                </div>
              </StaggerChild>
            </StaggerIn>
          </div>
        </div>

        {/* Scroll Indicator */}
        <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 2 }}
            className="absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-3"
        >
            <span className="text-[10px] font-mono font-black text-white/20 uppercase tracking-[0.4em]">Initialize Scroll</span>
            <div className="w-[1px] h-12 bg-gradient-to-b from-cyan-500/50 to-transparent" />
        </motion.div>
      </section>

      {/* ── Technology Section ─────────────────────────────────────────── */}
      <section id="technology" className="py-32 relative">
        <div className="max-w-7xl mx-auto px-6 relative z-10">
          <div className="text-center mb-24">
            <Badge variant="outline" className="mb-6">Methodology</Badge>
            <h2 className="text-4xl md:text-6xl font-black text-white mb-6 uppercase tracking-tight font-heading">
              Secure <span className="text-cyan-400">Ledger</span> Chain
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            {HOW_IT_WORKS.map((item, i) => (
              <motion.div
                key={item.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: 0.1 * i }}
                className="p-10 rounded-[3rem] border border-white/5 glass-panel group relative overflow-hidden transition-all duration-500 hover:border-cyan-500/20 hover:bg-cyan-500/[0.02]"
              >
                <div className="relative z-10 flex flex-col items-center text-center">
                  <div
                    className="w-16 h-16 rounded-2xl flex items-center justify-center mb-10 border transition-transform duration-500 group-hover:scale-110"
                    style={{
                      background: `rgba(${item.rgb}, 0.05)`,
                      borderColor: `rgba(${item.rgb}, 0.2)`,
                    }}
                  >
                    <item.icon className="w-8 h-8" style={{ color: item.color }} />
                  </div>
                  <p className="text-[10px] font-black tracking-[0.3em] text-white/20 uppercase mb-4 font-mono">
                    {item.tag}
                  </p>
                  <h3 className="text-xl font-black text-white mb-4 uppercase tracking-tight font-heading">
                    {item.title}
                  </h3>
                  <p className="text-sm text-white/30 leading-relaxed font-medium">
                    {item.desc}
                  </p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Agents Grid ─────────────────────────────────────────────────── */}
      <section id="agents" className="py-32 bg-white/[0.01] border-y border-white/5">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex flex-col md:flex-row items-end justify-between gap-8 mb-24">
            <div className="max-w-2xl">
               <Badge className="mb-6">The Collective</Badge>
               <h2 className="text-4xl md:text-6xl font-black text-white uppercase tracking-tight font-heading">
                 Neural <span className="text-cyan-400">Forensic</span> Units
               </h2>
            </div>
            <p className="text-white/30 text-sm font-medium max-w-sm pb-2">
              Our council consists of specialized neural networks trained on millions of authentic and manipulated samples.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {AGENTS.map((agent, i) => (
              <motion.div
                key={agent.id}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: i * 0.05 }}
                className="p-10 rounded-[3rem] bg-white/[0.01] border border-white/[0.05] hover:border-white/20 transition-all duration-500 group relative overflow-hidden"
              >
                <div className="flex flex-col items-center text-center">
                  <div className="flex items-center justify-center mb-8 relative">
                    <div
                      className="w-20 h-20 rounded-3xl flex items-center justify-center border transition-all duration-700 group-hover:rotate-[360deg]"
                      style={{
                        background: `rgba(${agent.bgRgb}, 0.08)`,
                        borderColor: `rgba(${agent.bgRgb}, 0.2)`,
                      }}
                    >
                      <agent.icon className="w-10 h-10" style={{ color: agent.color }} />
                    </div>
                  </div>
                  <Badge variant="secondary" size="sm" className="mb-4">{agent.badge}</Badge>
                  <h3 className="text-2xl font-black text-white mb-4 uppercase tracking-tighter font-heading">
                    {agent.name}
                  </h3>
                  <p className="text-white/30 text-sm font-medium leading-relaxed">
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
            onFileSelected={(f) => setSelectedFile(f)}
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
