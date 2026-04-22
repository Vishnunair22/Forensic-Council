"use client";

import { useState, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { UploadCloud } from "lucide-react";

import { AnalysisProgressOverlay } from "@/components/evidence/AnalysisProgressOverlay";
import { autoLoginAsInvestigator, checkBackendHealth, ProtocolWarmingError } from "@/lib/api";
import { __pendingFileStore } from "@/lib/pendingFileStore";
import { useSound } from "@/hooks/useSound";
import { storage, sessionOnlyStorage } from "@/lib/storage";

import { UploadModal } from "@/components/evidence/UploadModal";
import { UploadSuccessModal } from "@/components/evidence/UploadSuccessModal";

export function HeroAuthActions() {
  const router = useRouter();
  const [showUpload, setShowUpload] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isAuthenticating, setIsAuthenticating] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [isNavigating, setIsNavigating] = useState(false);
  const { playSound } = useSound();

  useEffect(() => {
    const resetHome = () => {
      setShowUpload(false);
      setSelectedFile(null);
      setIsAuthenticating(false);
      setAuthError(null);
    };

    const openUpload = () => {
      setShowUpload(true);
      setSelectedFile(null);
      setIsAuthenticating(false);
      setAuthError(null);
    };

    window.addEventListener("fc:reset-home", resetHome);
    window.addEventListener("fc:open-upload", openUpload);
    return () => {
      window.removeEventListener("fc:reset-home", resetHome);
      window.removeEventListener("fc:open-upload", openUpload);
    };
  }, []);

  const handleStartAnalysis = useCallback(async () => {
    if (!selectedFile) return;
    setShowUpload(false);
    setIsAuthenticating(true);
    setAuthError(null);

    try {
      const health = await checkBackendHealth();
      if (!health.ok) {
        setAuthError(health.warmingUp ? "Protocol Warming Up... (60s)" : health.message);
        setIsAuthenticating(false);
        return;
      }

      await autoLoginAsInvestigator();
      storage.setItem("forensic_auth_ok", "1");
    } catch (err) {
      if (process.env.NODE_ENV !== "production") console.error("Auto-login failed:", err);
      if (err instanceof ProtocolWarmingError) {
        setAuthError("Protocol Warming Up... (Retrying)");
      } else {
        const msg = err instanceof Error ? err.message : "Authentication failed";
        setAuthError(msg);
      }
      setIsAuthenticating(false);
      return;
    } finally {
      setIsAuthenticating(false);
    }

    __pendingFileStore.file = selectedFile;
    sessionOnlyStorage.setItem("forensic_auto_start", "true");
    sessionOnlyStorage.setItem("fc_show_loading", "true");
    setIsNavigating(true);
    router.push("/evidence", { scroll: true });
  }, [router, selectedFile]);

  return (
    <>
      <button
        onClick={() => {
          playSound("hum");
          setShowUpload(true);
        }}
        className="group px-14 py-6 text-base font-bold tracking-tighter uppercase relative overflow-hidden rounded-full bg-gradient-to-br from-[#14b8a6] to-[#0d9488] hover:bg-transparent hover:from-transparent hover:to-transparent text-white shadow-[0_0_40px_rgba(20,184,166,0.3)] transition-all duration-500 hover:scale-[1.05] hover:shadow-[0_0_60px_rgba(20,184,166,0.5)] border border-teal-400/40 hover:border-teal-400"
        aria-label={isAuthenticating ? "Initializing..." : authError ? authError : "Upload a file to begin analysis"}
      >
        {/* Scanning Line Effect within Button */}
        <motion.div 
          className="absolute inset-0 w-full h-[1px] bg-white/20 z-10"
          animate={{ top: ["0%", "100%", "0%"] }}
          transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
        />
        
        <span className="relative z-10 flex items-center gap-4">
          <UploadCloud className="w-5 h-5 group-hover:animate-bounce" />
          {isAuthenticating ? "Initializing..." : authError ? authError : "Begin Investigation"}
        </span>

        {/* Outer Glow on Hover */}
        <div className="absolute inset-0 bg-teal-400 opacity-0 group-hover:opacity-20 blur-2xl transition-opacity duration-500" />
      </button>

      <AnimatePresence>
        {(isAuthenticating || isNavigating) && (
          <AnalysisProgressOverlay
            isVisible={isAuthenticating || isNavigating}
            title={isNavigating ? "Neural Uplink Active" : "Initializing Protocol"}
            message={isNavigating ? "Routing To Analysis Workspace..." : (authError ?? "Authenticating Investigator...")}
          />
        )}
      </AnimatePresence>

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
    </>
  );
}
