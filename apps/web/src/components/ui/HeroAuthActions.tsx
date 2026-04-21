"use client";

import { useState, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence } from "framer-motion";
import { ArrowRight } from "lucide-react";

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
    window.addEventListener("fc:reset-home", resetHome);
    return () => window.removeEventListener("fc:reset-home", resetHome);
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
        className="flex items-center justify-center gap-2 px-8 py-4 min-h-[44px] rounded-full text-[15px] font-bold text-white bg-cyan-600 border border-cyan-600 hover:bg-transparent hover:text-cyan-500 hover:border-cyan-500 transition-all duration-200 shadow-[0_10px_30px_rgba(8,145,178,0.3)] active:scale-95 group"
        aria-label={isAuthenticating ? "Initializing..." : authError ? authError : "Upload a file to begin analysis"}
      >
        <span className="relative z-10 flex items-center">
          {isAuthenticating ? "Initializing..." : authError ? authError : "Begin Analysis"}
          {!isAuthenticating && !authError && <ArrowRight className="ml-2 w-5 h-5 group-hover:translate-x-1 transition-transform" aria-hidden="true" />}
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
