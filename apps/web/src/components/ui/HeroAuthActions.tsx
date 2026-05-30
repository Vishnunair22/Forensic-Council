"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";

import { useSound } from "@/hooks/useSound";
import { useQueryClient } from "@tanstack/react-query";
import { resetActiveInvestigation } from "@/lib/appReset";
import { toast } from "@/hooks/use-toast";
import { authService } from "@/lib/upload/authService";
import { fileHandoffManager } from "@/lib/upload/fileHandoffManager";
import { sessionOnlyStorage } from "@/lib/storage";
import { STORAGE_KEYS } from "@/lib/storageKeys";

import { UploadModal } from "@/components/evidence/UploadModal";
import { UploadSuccessModal } from "@/components/evidence/UploadSuccessModal";

export function HeroAuthActions() {
  const router = useRouter();
  const { playSound } = useSound();
  const queryClient = useQueryClient();

  const [showUpload, setShowUpload] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isHandingOff, setIsHandingOff] = useState(false);
  const [localAuthError, setLocalAuthError] = useState<string | null>(null);
  const [isAuthing, setIsAuthing] = useState(false);
  const sessionExpiredHandledRef = useRef(false);
  const ctaRef = useRef<HTMLButtonElement>(null);

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

  useEffect(() => {
    router.prefetch?.("/evidence");
  }, [router]);

  useEffect(() => {
    document.body.style.overflow = showUpload ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [showUpload]);

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
  }, [router, queryClient]);

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

  const handleStartAnalysis = useCallback(async () => {
    if (!selectedFile) return false;

    setIsHandingOff(true);

    try {
      await authService.ensureAuthenticated();
    } catch (error) {
      console.warn("[HeroAuthActions] auth failed in handleStartAnalysis:", error);
      toast.destructive({
        title: "Authentication Failed",
        description: error instanceof Error ? error.message : "Could not authenticate your credentials. Please try again.",
      });
      setIsHandingOff(false);
      return false;
    }

    await fileHandoffManager.prepareUpload(selectedFile);

    setShowUpload(false);
    sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_HANDOFF_FIRED);
    router.push("/evidence", { scroll: true });
    return true;
  }, [selectedFile, router]);

  const handleCTAClick = useCallback(async () => {
    setShowUpload(true);
    setSelectedFile(null);
    setIsHandingOff(false);
    setLocalAuthError(null);

    try {
      playSound("envelope-open");
    } catch { /* non-blocking */ }

    authService.reset();
    setIsAuthing(true);
    authService.ensureAuthenticated()
      .then(() => {
        setIsAuthing(false);
        setLocalAuthError(null);
      })
      .catch((err: unknown) => {
        setIsAuthing(false);
        const msg = err instanceof Error ? err.message : "Authentication failed";
        setLocalAuthError(msg);
      });
  }, [playSound]);

  const closeUpload = useCallback(() => {
    setShowUpload(false);
    setSelectedFile(null);
    setIsHandingOff(false);
    authService.reset();
    setLocalAuthError(null);
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
          onFocusOutside={(e) => e.preventDefault()}
        >
          <DialogTitle className="sr-only">
            {!selectedFile ? "Upload Evidence" : "Evidence Ready"}
          </DialogTitle>
          <DialogDescription className="sr-only">
            {!selectedFile
              ? "Drag and drop or browse to select an evidence file for forensic analysis."
              : "Evidence file has been received. Proceed to analysis or cancel."}
          </DialogDescription>
          <AnimatePresence mode="popLayout" initial={false}>
            {!selectedFile ? (
              <UploadModal
                key="upload-modal"
                onClose={closeUpload}
                onFileSelected={(file) => setSelectedFile(file)}
                authError={localAuthError}
              />
            ) : (
              <UploadSuccessModal
                key="success-modal"
                file={selectedFile}
                onDismiss={() => setSelectedFile(null)}
                isHandingOff={isHandingOff}
                authError={localAuthError}
                onStartAnalysis={async () => {
                  playSound("scan");
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
