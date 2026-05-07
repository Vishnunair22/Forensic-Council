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

export function HeroAuthActions() {
  const router = useRouter();
  const [showUpload, setShowUpload] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isAuthenticating, setIsAuthenticating] = useState(false);
  const [isNavigating, setIsNavigating] = useState(false);
  const [handoffVisible, setHandoffVisible] = useState(false);
  const [handoffText, setHandoffText] = useState("Uploading evidence to secure forensic pipeline...");
  const [isHandingOff, setIsHandingOff] = useState(false);
  const { playSound } = useSound();

  // Handle back-navigation events dispatched from the evidence page
  useEffect(() => {
    const resetHome = () => {
      setShowUpload(false);
      setSelectedFile(null);
      setIsAuthenticating(false);
      setHandoffVisible(false);
      setHandoffText("Uploading evidence to secure forensic pipeline...");
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

  // Pre-warm auth and prefetch evidence route on mount
  useEffect(() => {
    router.prefetch?.("/evidence");
    if (!__pendingFileStore.authPromise && !document.cookie.includes("access_token")) {
      __pendingFileStore.authPromise = autoLoginAsInvestigator().catch((e) => {
        console.warn("Pre-warm auth failed", e);
        __pendingFileStore.authPromise = null;
        throw e;
      });
    }
  }, [router]);

  // Re-open upload modal when returning from evidence page via ?upload=1 or fc_open_upload_once
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

  const handleStartAnalysis = useCallback(async () => {
    if (!selectedFile || isAuthenticating || isNavigating) return;
    setIsAuthenticating(true);
    setHandoffVisible(true);

    __pendingFileStore.file = selectedFile;
    // Resolve pre-warmed auth before navigating so the evidence page never
    // starts an investigation with a missing token. Failures are non-fatal —
    // the evidence page will retry auth independently.
    if (__pendingFileStore.authPromise) {
      try {
        await __pendingFileStore.authPromise;
      } catch {
        // swallowed — evidence page retries
      }
    }
    sessionOnlyStorage.setItem("forensic_auto_start", "true");
    sessionOnlyStorage.setItem("fc_show_loading", "true");
    setShowUpload(false);
    // Advance overlay to "Connecting" phase so the card transitions before navigation
    setHandoffText("Connecting to evidence analysis stream...");
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
            // Reuse pre-warmed auth promise or start a new one if missing
            __pendingFileStore.authPromise ||= autoLoginAsInvestigator().catch((e) => {
              console.error("Auth failed on click", e);
              __pendingFileStore.authPromise = null;
              throw e;
            });
          }}
          aria-label="Upload a file to begin analysis"
          className="btn-horizon-primary group relative select-none overflow-hidden"
        >
          <motion.div
            className="absolute inset-0 bg-primary/10 opacity-0 group-hover:opacity-100 transition-opacity duration-500"
          />

          <span className="relative z-10 flex items-center gap-4 text-[#020617]">
            {/* Envelope icon that flies up when upload modal is open */}
            <div className="relative w-6 h-6 overflow-hidden">
              <motion.div
                initial={false}
                animate={showUpload ? "open" : "closed"}
                variants={{
                  closed: { y: 0, rotateX: 0 },
                  open: { y: -20, rotateX: 180 },
                }}
                transition={{ duration: 0.4, ease: "backOut" }}
                className="absolute inset-0"
              >
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="w-6 h-6"
                >
                  <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
                  <polyline points="22,6 12,13 2,6" />
                </svg>
              </motion.div>
            </div>

            <span className="font-bold uppercase tracking-widest">Begin Analysis</span>

            <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
          </span>
        </motion.button>
      </div>

      <AnimatePresence>
        {showUpload && !selectedFile && !isHandingOff && (
          <UploadModal
            key="upload-modal"
            onClose={() => setShowUpload(false)}
            onFileSelected={(f) => setSelectedFile(f)}
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
              await new Promise((r) => setTimeout(r, 220));
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
