"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ArrowRight } from "lucide-react";

import { __pendingFileStore } from "@/lib/pendingFileStore";
import { useSound } from "@/hooks/useSound";
import { sessionOnlyStorage } from "@/lib/storage";
import { autoLoginAsInvestigator } from "@/lib/api";
import { clearInvestigationPersistence } from "@/lib/investigationStorage";

import { UploadModal } from "@/components/evidence/UploadModal";
import { UploadSuccessModal } from "@/components/evidence/UploadSuccessModal";
import { LoadingOverlay } from "@/components/ui/LoadingOverlay";

export function HeroAuthActions() {
  const router = useRouter();
  const { playSound } = useSound();
  const prefersReducedMotion = useReducedMotion();

  const [showUpload, setShowUpload] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isHandingOff, setIsHandingOff] = useState(false);
  const ctaRef = useRef<HTMLButtonElement>(null);

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

    clearInvestigationPersistence();
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
    __pendingFileStore.authError = null;
    __pendingFileStore.authPromise ||= autoLoginAsInvestigator()
      .then((token) => {
        __pendingFileStore.authError = null;
        return token;
      })
      .catch((err) => {
        const error = err instanceof Error ? err : new Error("Authentication failed");
        console.warn("[HeroAuthActions] pre-auth failed; evidence page will retry:", error);
        __pendingFileStore.authError = error;
        __pendingFileStore.authPromise = null;
        return Promise.resolve(null as never);
      });
  }, [playSound]);

  const closeUpload = useCallback(() => {
    setShowUpload(false);
    setSelectedFile(null);
    requestAnimationFrame(() => ctaRef.current?.focus());
  }, []);

  return (
    <>
      <motion.button
        ref={ctaRef}
        type="button"
        data-testid="hero-cta-begin"
        whileHover={prefersReducedMotion ? undefined : { scale: 1.02 }}
        whileTap={prefersReducedMotion ? undefined : { scale: 0.98 }}
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
            onClose={closeUpload}
            onFileSelected={(file) => setSelectedFile(file)}
          />
        )}

        {showUpload && selectedFile && !isHandingOff && (
          <UploadSuccessModal
            key="success-modal"
            file={selectedFile}
            onNewUpload={() => setSelectedFile(null)}
            onDismiss={closeUpload}
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
