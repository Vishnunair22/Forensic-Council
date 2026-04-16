"use client";

import { useState, useEffect, useCallback } from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence, useScroll } from "framer-motion";
import { ArrowRight } from "lucide-react";

import { ForensicProgressOverlay } from "@/components/ui/ForensicProgressOverlay";

import { autoLoginAsInvestigator, checkBackendHealth } from "@/lib/api";
import { __pendingFileStore } from "@/lib/pendingFileStore";
import { useForensicSfx } from "@/hooks/useForensicSfx";

import { StaggerIn, StaggerChild } from "@/components/ui/PageTransition";
import { HowWorksSection } from "@/components/ui/HowWorksSection";
import { AgentsSection } from "@/components/ui/AgentsSection";

import { UploadModal } from "@/components/evidence/UploadModal";
import { UploadSuccessModal } from "@/components/evidence/UploadSuccessModal";

export default function Home() {
  const router = useRouter();
  const [showUpload, setShowUpload] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isAuthenticating, setIsAuthenticating] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [isNavigating, setIsNavigating] = useState(false);
  const [isDeferred, setIsDeferred] = useState(true);
  const { scrollY } = useScroll();
  const [hasScrolled, setHasScrolled] = useState(false);
  const { playHum } = useForensicSfx();

  useEffect(() => {
    return scrollY.on("change", (latest: number) => {
      if (latest > 50 && !hasScrolled) setHasScrolled(true);
    });
  }, [scrollY, hasScrolled]);

  useEffect(() => {
    const resetHome = () => {
      setShowUpload(false);
      setSelectedFile(null);
      setIsAuthenticating(false);
      setAuthError(null);
      setHasScrolled(false);
    };
    window.addEventListener("fc:reset-home", resetHome);

    // Defer heavy background logic until after initial hydration
    const timer = setTimeout(() => setIsDeferred(false), 300);
    
    return () => {
      window.removeEventListener("fc:reset-home", resetHome);
      clearTimeout(timer);
    };
  }, []);

  const handleStartAnalysis = useCallback(async () => {
    if (!selectedFile) return;
    setIsAuthenticating(true);
    setAuthError(null);
    
    try {
      // 1. Check Backend Health first
      const health = await checkBackendHealth();
      if (!health.ok) {
        if (health.warmingUp) {
          setAuthError("Protocol Warming Up... (60s)");
          // Option: could loop here, but simple feedback is better for now
        } else {
          setAuthError(health.message);
        }
        setIsAuthenticating(false);
        return;
      }

      // 2. Perform Auto-login
      await autoLoginAsInvestigator();
      sessionStorage.setItem("forensic_auth_ok", "1");
    } catch (err) {
      console.error("Auto-login failed:", err);
      const msg = err instanceof Error ? err.message : "Authentication failed";
      
      // Recognition of Docker-internal warm-up period (common after docker-compose up)
      if (msg.includes("503") || msg.includes("timeout") || msg.includes("warm") || msg.includes("connect")) {
        setAuthError("Protocol Warming Up... (Retrying)");
      } else {
        setAuthError(msg);
      }
      
      setIsAuthenticating(false);
      return; 
    } finally {
      setIsAuthenticating(false);
    }

    __pendingFileStore.file = selectedFile;
    sessionStorage.setItem("forensic_auto_start", "true");
    sessionStorage.setItem("fc_show_loading", "true");
    setIsNavigating(true);
    router.push("/evidence", { scroll: true });
  }, [router, selectedFile]);

  return (
    <main className="min-h-screen selection:bg-cyan-500/30 selection:text-cyan-200 text-white pt-24 pb-32">

      {/* ── Hero Section ────────────────────────────────────────────────────── */}
      <section id="hero" className="relative h-screen overflow-hidden flex items-center justify-center pt-24">
        {/* Deep Field Ambience & Grids (2026 Standards) */}
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_40%,rgba(34,211,238,0.05)_0%,transparent_70%)] pointer-events-none" />
        <div className="absolute inset-0 bg-pulse pointer-events-none mix-blend-screen opacity-50" />
        <div className="absolute inset-0 pixel-grid pointer-events-none opacity-20 mix-blend-overlay" />
        <div className="scan-line-overlay" />
        
        <div className="max-w-7xl mx-auto px-6 relative z-10 w-full">
          <div className="max-w-4xl mx-auto text-center">
            <StaggerIn>
              <StaggerChild>
                <div className="flex flex-col items-center mb-2">
                   <h1 
                     className="flex flex-col items-center gap-1 md:gap-3 font-heading"
                     aria-label="Multi Agent Forensic Evidence Analysis System"
                   >
                      <span 
                        className="text-4xl md:text-7xl font-black tracking-tighter leading-[0.85] text-transparent bg-clip-text bg-gradient-to-b from-white to-white/70 text-glow pb-2"
                        aria-hidden="true"
                      >
                        Multi Agent Forensic
                      </span>
                      <span 
                        className="text-3xl md:text-6xl font-black tracking-tight leading-[0.9] text-sky-400"
                        aria-hidden="true"
                      >
                        Evidence Analysis
                      </span>
                   </h1>
                </div>
              </StaggerChild>
              
              <StaggerChild>
                <div className="glass-panel p-8 md:p-12 rounded-3xl max-w-4xl mx-auto flex flex-col items-center shadow-2xl relative overflow-hidden group/card">
                  {/* Subtle inner glow for tactile feel */}
                  <div className="absolute inset-0 bg-gradient-to-t from-sky-500/5 to-transparent opacity-0 group-hover/card:opacity-100 transition-opacity duration-700 pointer-events-none" />
                  
                  <p className="text-sm md:text-lg text-slate-300 leading-relaxed mb-8 font-medium text-center tracking-tight text-balance relative z-10">
                    Forensic Council utilizes specialized digital forensic agents
                    to analyse evidence and create cohesive, court-admissible reports. Our system uses surgical precision 
                    to dissect artifacts and cross-validate findings through an autonomous arbiter.
                  </p>

                  <div className="flex justify-center w-full relative z-10">
                    <button
                      type="button"
                      onClick={() => {
                        playHum();
                        setShowUpload(true);
                      }}
                      disabled={isAuthenticating}
                      className="btn-primary group disabled:opacity-60 disabled:cursor-not-allowed w-full sm:w-auto shadow-[0_0_20px_rgba(14,165,233,0.3)] hover:shadow-[0_0_30px_rgba(56,189,248,0.5)] transition-all duration-300"
                    >
                      <span>
                        {isAuthenticating
                          ? "Initializing Protocol..."
                          : authError
                            ? authError
                            : "Begin Analysis"}
                      </span>
                      {!isAuthenticating && !authError && (
                        <ArrowRight className="w-4 h-4 ml-1 group-hover:translate-x-1.5 transition-transform" />
                      )}
                    </button>
                  </div>
                </div>
              </StaggerChild>
            </StaggerIn>
          </div>
        </div>

        {/* Scroll Indicator */}
        <AnimatePresence>
          {!hasScrolled && (
            <motion.div 
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 20 }}
                transition={{ duration: 1, ease: "easeOut" }}
                className="absolute bottom-12 left-1/2 -translate-x-1/2 flex flex-col items-center gap-4"
            >
                <span className="text-[9px] font-mono font-bold text-white/20 uppercase tracking-[0.5em]">Scroll</span>
                <div className="relative w-[1px] h-16 bg-white/5 overflow-hidden">
                   <motion.div 
                      className="absolute top-0 left-0 w-full h-1/3 bg-gradient-to-b from-transparent via-cyan-400 to-transparent"
                      animate={{ top: ["-100%", "200%"] }}
                      transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
                   />
                </div>
            </motion.div>
          )}
        </AnimatePresence>
      </section>

      {/* ── How It Works Section ─────────────────────────────────────────── */}
      <HowWorksSection />

      {/* ── Meet The Agents Section ───────────────────────────────────────── */}
      <AgentsSection />

      {/* ── Auth / Health-check Progress Overlay ────────────────────────────── */}
      <AnimatePresence>
        {(isAuthenticating || isNavigating) && (
          <ForensicProgressOverlay
            variant="stream"
            title={isNavigating ? "Transmitting" : "Initializing"}
            liveText={isNavigating ? "Routing to Analysis Workspace..." : (authError ?? "Authenticating investigator…")}
            telemetryLabel="Forensic pipeline"
            showElapsed
          />
        )}
      </AnimatePresence>

      {/* ── Modals ──────────────────────────────────────────────────────────── */}
      <AnimatePresence>
        {showUpload && !selectedFile && (
          <UploadModal
            onClose={() => setShowUpload(false)}
            onFileSelected={(f) => setSelectedFile(f)}
          />
        )}
        {showUpload && selectedFile && (
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
