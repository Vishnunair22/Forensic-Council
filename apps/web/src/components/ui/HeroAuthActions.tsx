"use client";

import { useState, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight } from "lucide-react";

import { __pendingFileStore } from "@/lib/pendingFileStore";
import { useSound } from "@/hooks/useSound";
import { sessionOnlyStorage } from "@/lib/storage";
import { autoLoginAsInvestigator } from "@/lib/api/client";

import { UploadModal } from "@/components/evidence/UploadModal";
import { UploadSuccessModal } from "@/components/evidence/UploadSuccessModal";
import { LoadingOverlay } from "@/components/ui/LoadingOverlay";

const HANDOFF_TEXT = "Opening evidence analysis...";

export function HeroAuthActions() {
  const router = useRouter();
  const [showUpload, setShowUpload] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isAuthenticating, setIsAuthenticating] = useState(false);
  const [isNavigating, setIsNavigating] = useState(false);
  const [handoffVisible, setHandoffVisible] = useState(false);
  const [handoffText, setHandoffText] = useState(HANDOFF_TEXT);
  const [isHandingOff, setIsHandingOff] = useState(false);
  const { playSound } = useSound();

  useEffect(() => {
    const resetHome = () => {
      setShowUpload(false);
      setSelectedFile(null);
      setIsAuthenticating(false);
      setHandoffVisible(false);
      setHandoffText(HANDOFF_TEXT);
      setIsHandingOff(false);
    };

    const openUpload = () => {
      setShowUpload(true);
      setSelectedFile(null);
      setIsAuthenticating(false);
      setHandoffVisible(false);
      setIsHandingOff(false);
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

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const openUploadOnce = sessionOnlyStorage.getItem("fc_open_upload_once");
    if (params.get("upload") !== "1" && openUploadOnce !== "1") {
      sessionOnlyStorage.removeItem("forensic_auto_start");
      sessionOnlyStorage.removeItem("fc_show_loading");
      window.sessionStorage.removeItem("forensic_auto_start");
      window.sessionStorage.removeItem("fc_show_loading");
    }
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

  const handleStartAnalysis = useCallback(async () => {
    if (!selectedFile || isAuthenticating || isNavigating) return;
    setIsAuthenticating(true);
    setHandoffVisible(true);

    __pendingFileStore.file = selectedFile;
    sessionOnlyStorage.setItem("forensic_auto_start", "true");
    sessionOnlyStorage.setItem("fc_show_loading", "true");
    setShowUpload(false);
    setHandoffText(HANDOFF_TEXT);
    await new Promise<void>((resolve) => setTimeout(resolve, 380));
    setIsNavigating(true);
    router.push("/evidence", { scroll: true });
  }, [router, selectedFile, isAuthenticating, isNavigating]);

  return (
    <>
      <div className="flex flex-col items-center gap-4">
        <motion.button
          data-testid="hero-cta-begin"
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={() => {
            playSound("envelope-open");
            router.prefetch?.("/evidence");
            setShowUpload(true);
            setSelectedFile(null);
            setHandoffVisible(false);
            setIsHandingOff(false);
            __pendingFileStore.authPromise ||= autoLoginAsInvestigator().catch((error) => {
              console.error("Auth failed on click", error);
              __pendingFileStore.authPromise = null;
              throw error;
            });
          }}
          aria-label="Upload a file to begin analysis"
          className="btn-horizon-primary group relative select-none overflow-hidden"
        >
          <motion.div className="absolute inset-0 bg-primary/10 opacity-0 group-hover:opacity-100 transition-opacity duration-500" />

          <span className="relative z-10 flex items-center gap-4 text-[#020617]">
            <ArrowRight className="w-5 h-5 transition-transform group-hover:translate-x-1" />
            <span className="font-bold uppercase tracking-widest">Begin Analysis</span>
          </span>
        </motion.button>
      </div>

      <AnimatePresence>
        {showUpload && !selectedFile && !isHandingOff && (
          <UploadModal
            key="upload-modal"
            onClose={() => setShowUpload(false)}
            onFileSelected={(file) => setSelectedFile(file)}
          />
        )}
        {showUpload && selectedFile && !isAuthenticating && !isHandingOff && (
          <UploadSuccessModal
            key="success-modal"
            file={selectedFile}
            onNewUpload={() => { setSelectedFile(null); setIsHandingOff(false); }}
            onDismiss={() => { setShowUpload(false); setSelectedFile(null); setIsHandingOff(false); }}
            onStartAnalysis={async () => {
              setIsHandingOff(true);
              setHandoffVisible(true);
              playSound("envelope-close");
              await new Promise((resolve) => setTimeout(resolve, 220));
              await handleStartAnalysis();
            }}
          />
        )}
        {handoffVisible && (
          <LoadingOverlay
            key="handoff-overlay"
            variant="full"
            liveText={handoffText}
            exitDuration={0.15}
          />
        )}
      </AnimatePresence>
    </>
  );
}
