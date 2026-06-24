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
import { loadingOverlayController } from "@/lib/upload/loadingOverlayController";
import { sessionOnlyStorage } from "@/lib/storage";
import { STORAGE_KEYS } from "@/lib/storageKeys";
import { computeFileSha256 } from "@/lib/crypto/fileHash";

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
  const [selectedFileHash, setSelectedFileHash] = useState<string | null>(null);
  const [hashError, setHashError] = useState<string | null>(null);
  const [isHashComputing, setIsHashComputing] = useState(false);
  const sessionExpiredHandledRef = useRef(false);
  const ctaRef = useRef<HTMLButtonElement>(null);
  const isHandingOffRef = useRef(false);

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
      void resetActiveInvestigation(queryClient);
    }
  }, [queryClient]);

  useEffect(() => {
    router.prefetch?.("/evidence");
  }, [router]);

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
      void resetActiveInvestigation(queryClient);
      router.push("/session-expired");
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
    if (!selectedFile || isHandingOffRef.current) return false;

    if (!selectedFileHash) {
      toast.destructive({
        title: "Hash Not Ready",
        description: "The SHA-256 custody hash must be computed before analysis can begin.",
      });
      return false;
    }

    isHandingOffRef.current = true;
    setIsHandingOff(true);

    // Raise the global loading overlay FIRST so it is fully visible before the
    // dialog begins its 150ms fade-out. Previously setShowUpload(false) fired
    // before loadingOverlayController.show(), creating a gap where the
    // UploadSuccessModal was visible through the semi-transparent overlay during
    // its opacity:0→1 fade-in.
    loadingOverlayController.show("Opening evidence analysis…");

    // Now close the upload dialog — the overlay is already on screen.
    setShowUpload(false);

    try {
      await authService.ensureAuthenticated();
    } catch (error) {
      console.warn("[HeroAuthActions] auth failed in handleStartAnalysis:", error);
      toast.destructive({
        title: "Authentication Failed",
        description: error instanceof Error ? error.message : "Could not authenticate your credentials. Please try again.",
      });
      isHandingOffRef.current = false;
      setIsHandingOff(false);
      loadingOverlayController.forceDismiss();
      return false;
    }

    await fileHandoffManager.prepareUpload(selectedFile, {
      clientSha256: selectedFileHash,
    });

    // FC_HANDOFF_FIRED must be cleared so Effect A on /evidence (which skips when
    // it is already "1") actually runs, recovers the file, and starts analysis.
    sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_HANDOFF_FIRED);
    router.push("/evidence", { scroll: true });
    return true;
  }, [selectedFile, selectedFileHash, router]);

  const handleFileSelected = useCallback(async (file: File) => {
    setSelectedFile(file);
    setSelectedFileHash(null);
    setHashError(null);
    setIsHashComputing(true);
    try {
      const result = await computeFileSha256(file);
      setSelectedFileHash(result.hex);
      // Chime only once the evidence is truly sealed (validated + hashed),
      // so the success cue can never precede a hash failure.
      playSound("success-chime");
    } catch (err) {
      setHashError(err instanceof Error ? err.message : "Could not compute SHA-256.");
      playSound("error");
    } finally {
      setIsHashComputing(false);
    }
  }, [playSound]);

  const handleCTAClick = useCallback(async () => {
    setShowUpload(true);
    setSelectedFile(null);
    setIsHandingOff(false);
    setLocalAuthError(null);

    try {
      playSound("envelope-open");
    } catch { /* non-blocking */ }

    authService.reset();
    authService.ensureAuthenticated()
      .then(() => {
        setLocalAuthError(null);
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : "Authentication failed";
        setLocalAuthError(msg);
      });
  }, [playSound]);

  const closeUpload = useCallback(() => {
    setShowUpload(false);
    setSelectedFile(null);
    // Fully reset the modal's transient state on close so a re-open never
    // carries over a prior selection's hash/computation state.
    setSelectedFileHash(null);
    setHashError(null);
    setIsHashComputing(false);
    isHandingOffRef.current = false;
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
            {!selectedFile ? "Upload Evidence" : "Evidence Sealed"}
          </DialogTitle>
          <DialogDescription className="sr-only">
            {!selectedFile
              ? "Drag and drop or browse to select an evidence file for forensic analysis."
              : "Evidence file has been received. Proceed to analysis or cancel."}
          </DialogDescription>
          <AnimatePresence mode="wait" initial={false}>
            {!selectedFile ? (
              <UploadModal
                key="upload-modal"
                onClose={closeUpload}
                onFileSelected={handleFileSelected}
                authError={localAuthError}
              />
            ) : (
              <UploadSuccessModal
                key="success-modal"
                file={selectedFile}
                fileSha256={selectedFileHash}
                hashError={hashError}
                isHashComputing={isHashComputing}
                onDismiss={() => {
                  setSelectedFile(null);
                  setSelectedFileHash(null);
                  setHashError(null);
                }}
                onCancel={closeUpload}
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
