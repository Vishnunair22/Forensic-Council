"use client";

import { useState, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence } from "framer-motion";
import { ArrowRight, Loader2 } from "lucide-react";

import { __pendingFileStore } from "@/lib/pendingFileStore";
import { useSound } from "@/hooks/useSound";
import { sessionOnlyStorage } from "@/lib/storage";

import { UploadModal } from "@/components/evidence/UploadModal";
import { UploadSuccessModal } from "@/components/evidence/UploadSuccessModal";
import { ForensicErrorModal } from "@/components/ui/ForensicErrorModal";
import { LoadingOverlay } from "@/components/ui/LoadingOverlay";

export function HeroAuthActions() {
  const router = useRouter();
  const [showUpload, setShowUpload] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isAuthenticating, setIsAuthenticating] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [isNavigating, setIsNavigating] = useState(false);
  const [handoffVisible, setHandoffVisible] = useState(false);
  const { playSound } = useSound();

  useEffect(() => {
    const resetHome = () => {
      setShowUpload(false);
      setSelectedFile(null);
      setIsAuthenticating(false);
      setAuthError(null);
      setHandoffVisible(false);
    };

    const openUpload = () => {
      setShowUpload(true);
      setSelectedFile(null);
      setIsAuthenticating(false);
      setAuthError(null);
      setHandoffVisible(false);
      router.prefetch?.("/evidence");
    };

    window.addEventListener("fc:reset-home", resetHome);
    window.addEventListener("fc:open-upload", openUpload);
    return () => {
      window.removeEventListener("fc:reset-home", resetHome);
      window.removeEventListener("fc:open-upload", openUpload);
    };
  }, [router]);

  useEffect(() => {
    router.prefetch?.("/evidence");
  }, [router]);

  // Open the upload modal when navigated back with ?upload=1 (e.g. from handleNewUpload)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const openUploadOnce = sessionOnlyStorage.getItem("fc_open_upload_once");
    if (params.get("upload") === "1" || openUploadOnce === "1") {
      setShowUpload(true);
      setSelectedFile(null);
      if (openUploadOnce === "1") {
        sessionOnlyStorage.removeItem("fc_open_upload_once");
      }
      const url = new URL(window.location.href);
      if (url.searchParams.has("upload")) {
        url.searchParams.delete("upload");
        window.history.replaceState({}, "", url.toString());
      }
    }
  }, []);

  useEffect(() => {
    setIsNavigating(false);
    setIsAuthenticating(false);
  }, []);

  const handleStartAnalysis = useCallback(async () => {
    if (!selectedFile || isAuthenticating || isNavigating) return;
    setIsAuthenticating(true);
    setAuthError(null);
    setHandoffVisible(true);

    __pendingFileStore.file = selectedFile;
    sessionOnlyStorage.setItem("forensic_auto_start", "true");
    sessionOnlyStorage.setItem("fc_show_loading", "true");
    setShowUpload(false);
    setIsNavigating(true);
    await new Promise<void>((resolve) => {
      requestAnimationFrame(() => resolve());
    });
    router.push("/evidence", { scroll: true });
  }, [router, selectedFile, isAuthenticating, isNavigating]);

  return (
    <>
      <div className="flex flex-col items-center gap-4">
        <button
          data-testid="hero-cta-begin"
          onClick={() => {
            playSound("envelope-open");
            router.prefetch?.("/evidence");
            setShowUpload(true);
            setSelectedFile(null);
            setAuthError(null);
            setHandoffVisible(false);
          }}
          aria-label={isAuthenticating ? "Initializing..." : authError ? authError : "Upload a file to begin analysis"}
          className="btn-horizon-primary group relative select-none"
        >
          <span className="relative z-10 flex items-center gap-3 text-[#020617]">
            <span className="font-bold uppercase tracking-widest">
              {isAuthenticating ? "Initializing..." : authError ? authError : "Begin Analysis"}
            </span>
            {isAuthenticating ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
            )}
          </span>
        </button>

      </div>

      <ForensicErrorModal
        isVisible={!!authError}
        title="Protocol Initialization Failure"
        message={authError || "Could not establish secure investigator session."}
        errorCode="0xFC_AUTH_INIT"
        onRetry={handleStartAnalysis}
        onHome={() => { setAuthError(null); setSelectedFile(null); }}
      />

      <AnimatePresence mode="sync">
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
            onStartAnalysis={async () => {
              playSound("envelope-close");
              await handleStartAnalysis();
            }}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {handoffVisible && (
          <LoadingOverlay
            liveText="Opening evidence analysis and preparing live backend stream..."
            dispatchedCount={0}
            totalAgents={5}
          />
        )}
      </AnimatePresence>
    </>
  );
}
