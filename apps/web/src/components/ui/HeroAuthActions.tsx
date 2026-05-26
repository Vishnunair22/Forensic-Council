"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

import { __pendingFileStore } from "@/lib/pendingFileStore";
import { useSound } from "@/hooks/useSound";
import { sessionOnlyStorage } from "@/lib/storage";
import { STORAGE_KEYS } from "@/lib/storageKeys";
import { autoLoginAsInvestigator } from "@/lib/api";
import { clearInvestigationPersistence } from "@/lib/investigationStorage";
import { savePendingEvidenceFile } from "@/lib/pendingFilePersistence";

import { useQueryClient } from "@tanstack/react-query";
import { resetActiveInvestigation } from "@/lib/appReset";
import { toast } from "@/hooks/use-toast";

import { UploadModal } from "@/components/evidence/UploadModal";
import { UploadSuccessModal } from "@/components/evidence/UploadSuccessModal";

export function HeroAuthActions() {
  const router = useRouter();
  const { playSound } = useSound();
  const queryClient = useQueryClient();

  const [showUpload, setShowUpload] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const sessionExpiredHandledRef = useRef(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("session_expired") === "true" && !sessionExpiredHandledRef.current) {
      sessionExpiredHandledRef.current = true;
      const url = new URL(window.location.href);
      url.searchParams.delete("session_expired");
      window.history.replaceState({}, "", url.toString());

      toast.destructive({
        title: "Session Expired",
        description: "Your session has expired due to inactivity. Please begin a new analysis.",
      });

      resetActiveInvestigation(queryClient);
    }
  }, [queryClient]);
  const [isHandingOff, setIsHandingOff] = useState(false);
  const ctaRef = useRef<HTMLButtonElement>(null);

  // Prefetch the evidence route once on mount
  useEffect(() => {
    router.prefetch?.("/evidence");
  }, [router]);

  // Manage body scroll lock centrally — no race between modal mounts/unmounts
  useEffect(() => {
    document.body.style.overflow = showUpload ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [showUpload]);

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
    const handleSessionExpired = () => {
      const queryClient = undefined;
      resetActiveInvestigation(queryClient);
      router.push("/?session_expired=true");
    };
    window.addEventListener("fc:reset-home", handleReset);
    window.addEventListener("fc:open-upload", handleOpen);
    window.addEventListener("fc:session-expired", handleSessionExpired);
    return () => {
      window.removeEventListener("fc:reset-home", handleReset);
      window.removeEventListener("fc:open-upload", handleOpen);
      window.removeEventListener("fc:session-expired", handleSessionExpired);
    };
  }, [router]);

  // Auto-open upload modal when returning from evidence page via ?upload=1.
  // IMPORTANT: never clear AUTO_START or FC_SHOW_LOADING here — those are
  // ephemeral flow-control flags managed by useInvestigation/handleStartAnalysis
  // during route transitions. Clearing them here races against router.push and
  // causes the loading overlay to flicker and the evidence page to lose its
  // auto-start signal (the "loading loop" bug).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const openOnce = sessionOnlyStorage.getItem(STORAGE_KEYS.FC_OPEN_UPLOAD_ONCE);

    if (params.get("upload") === "1" || openOnce === "1") {
      setShowUpload(true);
      setSelectedFile(null);
      if (openOnce === "1") sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_OPEN_UPLOAD_ONCE);
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
    try {
      await savePendingEvidenceFile(selectedFile);
    } catch (error) {
      console.warn("[HeroAuthActions] could not persist pending file:", error);
    }
    sessionOnlyStorage.setItem(STORAGE_KEYS.AUTO_START, "true");
    sessionOnlyStorage.setItem(STORAGE_KEYS.FC_SHOW_LOADING, "true");
    sessionOnlyStorage.setItem(
      STORAGE_KEYS.FC_PENDING_FILE_META,
      JSON.stringify({
        name: selectedFile.name,
        type: selectedFile.type,
        size: selectedFile.size,
        updatedAt: Date.now(),
      }),
      true,
    );

    setShowUpload(false);
    router.push("/evidence", { scroll: true });
  }, [selectedFile, router]);

  const handleCTAClick = useCallback(() => {
    setShowUpload(true);
    setSelectedFile(null);
    setIsHandingOff(false);
    try {
      playSound("envelope-open");
    } catch (error) {
      console.warn("[HeroAuthActions] non-blocking CTA sound failed:", error);
    }
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
        return Promise.reject(error);
      });
  }, [playSound]);

  const closeUpload = useCallback(() => {
    setShowUpload(false);
    setSelectedFile(null);
    setIsHandingOff(false);
    __pendingFileStore.authPromise = null;
    __pendingFileStore.authError = null;
    requestAnimationFrame(() => ctaRef.current?.focus());
  }, []);

  return (
    <>
      <button
        ref={ctaRef}
        type="button"
        data-testid="hero-cta-begin"
        onClick={handleCTAClick}
        aria-label="Upload a file to begin analysis"
        className="group fc-btn-primary gap-3 px-10"
      >
        <span>Begin Analysis</span>
        <ArrowRight className="w-4 h-4 fc-transition opacity-70 group-hover:opacity-100" aria-hidden="true" />
      </button>

      <Dialog
        open={showUpload}
        onOpenChange={(open) => { if (!open) closeUpload(); }}
      >
        <DialogContent
          className="max-w-xl p-0"
          aria-describedby="dialog-description"
          onFocusOutside={(e) => e.preventDefault()}
        >
          <DialogTitle className="sr-only">
            {!selectedFile ? "Upload Evidence" : "Evidence Ready"}
          </DialogTitle>
          <p id="dialog-description" className="sr-only">
            {!selectedFile
              ? "Drag and drop or browse to select an evidence file for forensic analysis."
              : "Evidence file has been received. Proceed to analysis or cancel."}
          </p>
          <AnimatePresence mode="wait" initial={false}>
            {!selectedFile ? (
              <UploadModal
                key="upload-modal"
                onClose={closeUpload}
                onFileSelected={(file) => setSelectedFile(file)}
              />
            ) : (
              <UploadSuccessModal
                key="success-modal"
                file={selectedFile}
                onDismiss={() => setSelectedFile(null)}
                isHandingOff={isHandingOff}
                  onStartAnalysis={async () => {
                  if (isHandingOff) return;
                  playSound("scan");
                  setIsHandingOff(true);
                  window.dispatchEvent(
                    new CustomEvent("fc_storage_update", {
                      detail: { key: STORAGE_KEYS.FC_SHOW_LOADING, value: "true" },
                    }),
                  );
                  await handleStartAnalysis();
                }}
              />
            )}
          </AnimatePresence>
        </DialogContent>
      </Dialog>

    </>
  );
}
