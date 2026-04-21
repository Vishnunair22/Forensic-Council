"use client";

import { useState, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence } from "framer-motion";
import { UploadCloud } from "lucide-react";

import { ForensicProgressOverlay } from "@/components/ui/ForensicProgressOverlay";
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
        className="group relative flex items-center justify-center px-12 py-5 rounded-full font-black text-[11px] tracking-[0.3em] uppercase overflow-hidden transition-all duration-500 hover:scale-[1.02] active:scale-[0.98] shadow-[0_0_40px_rgba(34,211,238,0.15)] hover:shadow-[0_0_60px_rgba(34,211,238,0.25)] border border-primary/20 hover:border-primary/40"
        aria-label={isAuthenticating ? "Initializing..." : authError ? authError : "Upload a file to begin analysis"}
      >
        {/* Background Gradient Layer */}
        <div className="absolute inset-0 bg-gradient-to-r from-[#22d3ee] to-[#3b82f6] opacity-90 group-hover:opacity-100 transition-opacity" />
        
        {/* Inner Glow/Shine Effect */}
        <div className="absolute inset-0 bg-gradient-to-b from-white/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-700" />

        <span className="relative z-10 flex items-center gap-3 text-black">
          <UploadCloud className="w-4 h-4 transition-transform duration-500 group-hover:-translate-y-0.5" />
          {isAuthenticating ? "Initializing..." : authError ? authError : "Begin Analysis"}
        </span>
      </button>

      <AnimatePresence>
        {(isAuthenticating || isNavigating) && (
          <ForensicProgressOverlay
            variant="stream"
            title={isNavigating ? "Transmitting" : "Initializing"}
            liveText={isNavigating ? "Routing To Analysis Workspace..." : (authError ?? "Authenticating Investigator...")}
            telemetryLabel="Forensic pipeline"
            showElapsed
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
