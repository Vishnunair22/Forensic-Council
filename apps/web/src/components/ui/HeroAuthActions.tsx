"use client";

import { useState, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight } from "lucide-react";

import { __pendingFileStore } from "@/lib/pendingFileStore";
import { useSound } from "@/hooks/useSound";
import { sessionOnlyStorage } from "@/lib/storage";
import { autoLoginAsInvestigator } from "@/lib/api";

import { UploadModal } from "@/components/evidence/UploadModal";
import { UploadSuccessModal } from "@/components/evidence/UploadSuccessModal";
import { LoadingOverlay } from "@/components/ui/LoadingOverlay";

export function HeroAuthActions() {
  const router = useRouter();
  const { playSound } = useSound();

  const [showUpload, setShowUpload] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isHandingOff, setIsHandingOff] = useState(false);

  // Prefetch the evidence route once on mount
  useEffect(() => {
    router.prefetch?.("/evidence");
  }, [router]);

  // Manage body scroll lock centrally — no race between modal mounts/unmounts
  useEffect(() => {
    document.body.style.overflow = showUpload || isHandingOff ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [showUpload, isHandingOff]);

  // Listen for global reset and open-upload events dispatched by navbar / session-expired
  useEffect(() => {
    const handleReset = () => {
      setShowUpload(false);
      setSelectedFile(null);
      setIsHandingOff(false);
    };
    const handleOpen = () => {
      setShowUpload(true);
      setSelectedFile(null);
      setIsHandingOff(false);
      router.prefetch?.("/evidence");
    };
    window.addEventListener("fc:reset-home", handleReset);
    window.addEventListener("fc:open-upload", handleOpen);
    return () => {
      window.removeEventListener("fc:reset-home", handleReset);
      window.removeEventListener("fc:open-upload", handleOpen);
    };
  }, [router]);

  // Auto-open upload modal when returning from evidence page via ?upload=1
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const openOnce = sessionOnlyStorage.getItem("fc_open_upload_once");

    if (params.get("upload") !== "1" && openOnce !== "1") {
      sessionOnlyStorage.removeItem("forensic_auto_start");
      sessionOnlyStorage.removeItem("fc_show_loading");
    }
    if (params.get("upload") === "1" || openOnce === "1") {
      setShowUpload(true);
      setSelectedFile(null);
      if (openOnce === "1") sessionOnlyStorage.removeItem("fc_open_upload_once");
      const url = new URL(window.location.href);
      if (url.searchParams.has("upload")) {
        url.searchParams.delete("upload");
        window.history.replaceState({}, "", url.toString());
      }
    }
  }, []);

  // Core handoff: store file, set session flags, then navigate
  const handleStartAnalysis = useCallback(async () => {
    if (!selectedFile) return;

    __pendingFileStore.file = selectedFile;
    sessionOnlyStorage.setItem("forensic_auto_start", "true");
    sessionOnlyStorage.setItem("fc_show_loading", "true");

    // Brief pause so the loading overlay is visible before navigation
    await new Promise<void>((resolve) => setTimeout(resolve, 560));
    router.push("/evidence", { scroll: true });
  }, [selectedFile, router]);

  const handleCTAClick = useCallback(() => {
    playSound("envelope-open");
    setShowUpload(true);
    setSelectedFile(null);
    setIsHandingOff(false);
    // Kick off auth in parallel — evidence page will await this promise
    __pendingFileStore.authPromise ||= autoLoginAsInvestigator().catch((err) => {
      console.error("[HeroAuthActions] pre-auth failed:", err);
      __pendingFileStore.authPromise = null;
      throw err;
    });
  }, [playSound]);

  return (
    <>
      <motion.button
        type="button"
        data-testid="hero-cta-begin"
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        onClick={handleCTAClick}
        aria-label="Upload a file to begin analysis"
        className="btn-horizon-primary group relative select-none overflow-hidden"
      >
        <motion.div
          className="absolute inset-0 bg-primary/10 opacity-0 group-hover:opacity-100 transition-opacity duration-500"
          aria-hidden="true"
        />
        <span className="relative z-10 flex items-center gap-4 text-[#020617]">
          <ArrowRight className="w-5 h-5 transition-transform group-hover:translate-x-1" aria-hidden="true" />
          <span className="font-bold uppercase tracking-widest">Begin Analysis</span>
        </span>
      </motion.button>

      <AnimatePresence>
        {showUpload && !selectedFile && !isHandingOff && (
          <UploadModal
            key="upload-modal"
            onClose={() => setShowUpload(false)}
            onFileSelected={(file) => setSelectedFile(file)}
          />
        )}

        {showUpload && selectedFile && !isHandingOff && (
          <UploadSuccessModal
            key="success-modal"
            file={selectedFile}
            onNewUpload={() => setSelectedFile(null)}
            onDismiss={() => { setShowUpload(false); setSelectedFile(null); }}
            onStartAnalysis={async () => {
              if (isHandingOff) return;
              playSound("envelope-close");
              setIsHandingOff(true);
              setShowUpload(false);
              await handleStartAnalysis();
            }}
          />
        )}

        {isHandingOff && (
          <LoadingOverlay
            key="handoff-overlay"
            liveText="Opening evidence analysis..."
            exitDuration={0.15}
          />
        )}
      </AnimatePresence>
    </>
  );
}
