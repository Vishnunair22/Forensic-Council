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
        className="group px-12 py-5 text-sm font-bold tracking-[0.1em] uppercase relative overflow-hidden rounded-full bg-black/50 backdrop-blur-md text-white transition-all duration-500 hover:scale-[1.02] border border-primary/30 hover:border-primary hover:shadow-[0_0_40px_rgba(0,255,65,0.2)]"
        aria-label={isAuthenticating ? "Initializing..." : authError ? authError : "Upload a file to begin analysis"}
      >
        {/* Update Scanning Line Color */}
        <motion.div 
          className="absolute inset-0 w-full h-[1px] bg-primary/40 z-10"
          animate={{ top: ["0%", "100%", "0%"] }}
          transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
        />
        
        <span className="relative z-10 flex items-center gap-3">
          <UploadCloud className="w-5 h-5 text-primary group-hover:animate-pulse" />
          {isAuthenticating ? "Initializing..." : authError ? authError : "Begin Investigation"}
        </span>

        {/* Outer Glow Update */}
        <div className="absolute inset-0 bg-primary opacity-0 group-hover:opacity-10 blur-xl transition-opacity duration-700" />
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
