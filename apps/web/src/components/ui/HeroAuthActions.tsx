"use client";

import { useState, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence } from "framer-motion";
import { UploadCloud, ArrowRight, Loader2 } from "lucide-react";

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
          playSound("envelope-open");
          setShowUpload(true);
        }}
        aria-label={isAuthenticating ? "Initializing..." : authError ? authError : "Upload a file to begin analysis"}
        className="group relative inline-flex items-center gap-3 px-8 py-4 rounded-full 
                   bg-info text-white font-bold text-base tracking-wide
                   hover:bg-transparent hover:text-info border border-transparent hover:border-info
                   active:scale-[0.98] transition-all duration-300
                   shadow-[0_0_30px_rgba(0,163,255,0.25)] hover:shadow-[0_0_50px_rgba(0,163,255,0.4)]
                   min-h-[52px] select-none"
      >
        <span className="relative z-10 flex items-center gap-3">
          <span className="font-bold">
            {isAuthenticating ? "Initializing..." : authError ? authError : "Begin Analysis"}
          </span>
          {isAuthenticating ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
          )}
        </span>

        {/* Outer Glow Update */}
        <div className="absolute inset-0 bg-info opacity-0 group-hover:opacity-10 blur-xl transition-opacity duration-700" />
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
            key="upload-modal" // Crucial for mode="wait" to track component lifecycle
            onClose={() => setShowUpload(false)}
            onFileSelected={(f) => {
              playSound("success-chime"); // The soft, elegant success sound
              setSelectedFile(f);
            }}
          />
        )}
        {showUpload && selectedFile && (
          <UploadSuccessModal
            key="success-modal"
            file={selectedFile}
            onNewUpload={() => setSelectedFile(null)}
            onStartAnalysis={() => {
              playSound("envelope-close"); // The locking seal sound before routing
              handleStartAnalysis();
            }}
          />
        )}
      </AnimatePresence>
    </>
  );
}
