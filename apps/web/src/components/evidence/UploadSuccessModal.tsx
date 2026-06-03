"use client";

import { useCallback, useState, useEffect, useRef } from "react";
import Image from "next/image";
import { motion, useReducedMotion } from "framer-motion";
import { Lock, ArrowRight, ArrowLeft, Image as ImageFileIcon } from "lucide-react";
import { useSound } from "@/hooks/useSound";
import { formatBytes } from "@/lib/utils";
import { TRANSITION_SMOOTH, SPRING_GENTLE } from "@/lib/animations";

export interface UploadSuccessModalProps {
  file: File;
  fileSha256: string | null;
  hashError?: string | null;
  isHashComputing?: boolean;
  onStartAnalysis: () => Promise<void> | void;
  onDismiss: () => void;
  isHandingOff?: boolean;
  authError?: string | null;
}

export function UploadSuccessModal({
  file,
  fileSha256,
  hashError,
  isHashComputing = false,
  onStartAnalysis,
  onDismiss,
  isHandingOff = false,
  authError,
}: UploadSuccessModalProps) {
  const { playSound } = useSound();
  const prefersReducedMotion = useReducedMotion();
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  // Move focus into the freshly-swapped content so screen readers announce the
  // state change ("Evidence Sealed") and keyboard focus is not orphaned on the
  // unmounted dropzone. Deferred a frame to win against Radix's focus trap.
  useEffect(() => {
    const raf = requestAnimationFrame(() => headingRef.current?.focus());
    return () => cancelAnimationFrame(raf);
  }, []);

  // Only image evidence reaches this modal — validateEvidenceFile rejects every
  // other MIME type upstream, so an object URL is only ever needed for images.
  useEffect(() => {
    if (!file.type.startsWith("image/")) return;
    const url = URL.createObjectURL(file);
    setObjectUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const closeModal = useCallback(() => {
    playSound("click");
    onDismiss();
  }, [playSound, onDismiss]);

  const extension = file.name.includes(".") ? file.name.substring(file.name.lastIndexOf(".")).toLowerCase() : "";

  return (
    <motion.div
      key="success-state"
      initial={prefersReducedMotion ? false : { opacity: 0, scale: 0.95, filter: "blur(4px)" }}
      animate={prefersReducedMotion ? false : { opacity: 1, scale: 1, filter: "blur(0px)" }}
      exit={prefersReducedMotion ? {} : { opacity: 0, scale: 1.05, filter: "blur(4px)" }}
      transition={TRANSITION_SMOOTH}
      className="p-6 sm:p-8 flex flex-col text-left relative overflow-y-auto custom-scrollbar max-h-[90vh] md:max-h-none"
    >
      <div className="absolute inset-0 opacity-[0.03] pointer-events-none bg-[radial-gradient(#fff_1px,transparent_1px)] [background-size:16px_16px]" aria-hidden="true" />

      <button
        type="button"
        onClick={closeModal}
        aria-label="Reselect file"
        data-testid="success-modal-close"
        className="absolute top-4 right-4 z-20 inline-flex items-center gap-1.5 h-8 px-3 rounded-full text-xs font-medium fc-text-muted hover:fc-text-primary hover:bg-white/5 border border-transparent hover:border-white/10 fc-transition fc-focus-ring cursor-pointer"
      >
        <ArrowLeft className="w-3.5 h-3.5" aria-hidden="true" />
        <span>Reselect</span>
      </button>

      <div className="mb-5 flex items-center justify-between relative z-10">
        <div className="flex items-center gap-3">
          <motion.div
            initial={prefersReducedMotion ? false : { rotate: -90, opacity: 0 }}
            animate={prefersReducedMotion ? false : { rotate: 0, opacity: 1 }}
            transition={{ duration: 0.4, delay: 0.1 }}
            className="w-9 h-9 rounded-full bg-primary/10 border border-primary/30 flex items-center justify-center text-primary"
          >
            <Lock className="w-5 h-5" aria-hidden="true" />
          </motion.div>
          <div>
            <p className="text-xs font-mono fc-text-muted uppercase tracking-wider">Status: Secured</p>
            <h2 ref={headingRef} tabIndex={-1} className="text-lg font-heading font-bold fc-text-primary outline-none">Evidence Sealed</h2>
          </div>
        </div>
      </div>

      <div className="bg-white/[0.03] border border-white/10 rounded-xl overflow-hidden mb-6">
        <div className="relative overflow-hidden bg-black/30 border-b border-white/5 min-h-[180px] max-h-[260px] flex items-center justify-center">
          <motion.div
            className="absolute inset-0 flex flex-col items-center justify-center"
            initial={prefersReducedMotion ? false : { scale: 0.9, opacity: 0, filter: "blur(4px)" }}
            animate={prefersReducedMotion ? false : { scale: 1, opacity: 1, filter: "blur(0px)" }}
            transition={SPRING_GENTLE}
          >
            {objectUrl ? (
              <>
                <Image
                  src={objectUrl}
                  alt={file.name}
                  fill
                  sizes="(max-width: 640px) 100vw, 640px"
                  unoptimized
                  className="object-cover"
                />
                {!prefersReducedMotion && (
                  <motion.div
                    initial={{ top: "0%", opacity: 1 }}
                    animate={{ top: "100%", opacity: 0 }}
                    transition={{ duration: 1.5, ease: "easeInOut" }}
                    className="absolute left-0 right-0 h-[2px] bg-primary/80 shadow-[0_0_8px_var(--color-primary)] pointer-events-none z-10"
                    aria-hidden="true"
                  />
                )}
              </>
            ) : (
              <div className="flex flex-col items-center justify-center p-4 text-center">
                <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-primary/20 to-primary/10 border border-primary/30 text-primary flex items-center justify-center mb-2">
                  <ImageFileIcon className="w-7 h-7" aria-hidden="true" />
                </div>
                <span className="text-xs font-mono tracking-wider fc-text-muted uppercase">
                  Image Evidence
                </span>
              </div>
            )}
          </motion.div>
        </div>

        <div className="p-4 flex flex-col gap-2">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-sm font-semibold fc-text-primary truncate max-w-[65%]" title={file.name}>
              {file.name}
            </span>
            {extension && (
              <span className="fc-badge fc-badge-active shrink-0 text-xs px-1.5 py-0">
                {extension}
              </span>
            )}
            <span className="text-xs font-mono fc-text-muted ml-auto">
              {formatBytes(file.size)}
            </span>
          </div>
          <div className="pt-2 border-t border-white/5 flex flex-col gap-1">
            <span className="text-xs font-mono fc-text-muted uppercase tracking-wider">
              SHA-256 Checksum
            </span>
            <motion.span
              initial={prefersReducedMotion ? false : { opacity: 0 }}
              animate={prefersReducedMotion ? false : { opacity: 1 }}
              transition={{ delay: prefersReducedMotion ? 0 : 0.15 }}
              className="text-xs font-mono text-primary truncate flex items-center gap-2"
              title={fileSha256 ?? undefined}
            >
              {isHashComputing ? (
                <>
                  <span className="w-3 h-3 rounded-full border border-primary border-t-transparent animate-spin" />
                  <span className="text-primary/60">Calculating SHA-256...</span>
                </>
              ) : hashError ? (
                <span className="text-red-400">Hash unavailable — reselect file</span>
              ) : fileSha256 ? (
                `${fileSha256.slice(0, 24).toLowerCase()}...${fileSha256.slice(-12).toLowerCase()}`
              ) : (
                <span className="text-primary/60">Waiting...</span>
              )}
            </motion.span>
          </div>
        </div>
      </div>

      {authError && (
        <div
          className="mb-6 p-4 rounded-xl border border-danger/20 bg-danger/5 text-sm fc-text-danger relative z-10"
          role="alert"
        >
          <strong>Authentication Error:</strong> {authError}. Please close the modal and try again to establish a valid investigator session.
        </div>
      )}

      <div className="flex gap-3 relative z-10 mt-auto">
        <button type="button" onClick={closeModal} className="fc-btn-secondary flex-1 text-sm py-2">
          Cancel
        </button>
        <button
          type="button"
          onClick={onStartAnalysis}
          disabled={isHandingOff || isHashComputing || !!hashError || !fileSha256}
          data-testid="upload-start-analysis"
          className="fc-btn-primary flex-[2] group relative overflow-hidden text-sm py-2"
        >
          <span className="relative z-10 flex items-center justify-center gap-2">
            {isHandingOff ? "Initializing Agents..." : "Deploy Council"}
            {!isHandingOff && <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" aria-hidden="true" />}
          </span>
          <div className="absolute inset-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300 ease-out" aria-hidden="true" />
        </button>
      </div>
    </motion.div>
  );
}
