"use client";

import { useCallback, useState, useEffect, useRef } from "react";
import Image from "next/image";
import { motion, useReducedMotion } from "framer-motion";
import {
  Lock,
  ArrowRight,
  ArrowLeft,
  Image as ImageFileIcon,
  Music,
  Video,
  FileText,
} from "lucide-react";
import { useSound } from "@/hooks/useSound";
import { formatBytes } from "@/lib/utils";
import { getFileCategory } from "@/lib/fileValidation";
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

  const fileCategory = getFileCategory(file.type);
  const extension = file.name.includes(".")
    ? file.name.substring(file.name.lastIndexOf(".")).toLowerCase()
    : "";

  // Move focus into the freshly-swapped content so screen readers announce the
  // state change ("Evidence Sealed") and keyboard focus is not orphaned.
  useEffect(() => {
    const raf = requestAnimationFrame(() => headingRef.current?.focus());
    return () => cancelAnimationFrame(raf);
  }, []);

  // Object URL only for image evidence — revoked on unmount.
  useEffect(() => {
    if (fileCategory !== "image") return;
    const url = URL.createObjectURL(file);
    setObjectUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file, fileCategory]);

  const closeModal = useCallback(() => {
    playSound("click");
    onDismiss();
  }, [playSound, onDismiss]);

  return (
    <motion.div
      key="success-state"
      initial={prefersReducedMotion ? false : { opacity: 0, scale: 0.96, y: 10, filter: "blur(4px)" }}
      animate={prefersReducedMotion ? false : { opacity: 1, scale: 1, y: 0, filter: "blur(0px)" }}
      exit={prefersReducedMotion ? {} : { opacity: 0, scale: 1.02, y: -6, filter: "blur(4px)" }}
      transition={TRANSITION_SMOOTH}
      className="p-6 sm:p-8 flex flex-col text-left relative"
    >
      {/* Subtle dot texture */}
      <div
        className="absolute inset-0 opacity-[0.03] pointer-events-none bg-[radial-gradient(#fff_1px,transparent_1px)] [background-size:16px_16px]"
        aria-hidden="true"
      />

      {/* ── Reselect button ── */}
      <button
        type="button"
        onClick={closeModal}
        aria-label="Reselect a different file"
        data-testid="success-modal-close"
        className="absolute top-4 right-4 z-20 inline-flex items-center gap-1.5 h-9 px-3 min-w-[44px] rounded-full text-xs font-medium fc-text-muted hover:fc-text-primary hover:bg-white/5 border border-transparent hover:border-white/10 fc-transition fc-focus-ring cursor-pointer"
      >
        <ArrowLeft className="w-3.5 h-3.5" aria-hidden="true" />
        <span>Reselect</span>
      </button>

      {/* ── Status header ── */}
      <div className="mb-5 flex items-center gap-3 relative z-10">
        <motion.div
          initial={prefersReducedMotion ? false : { rotate: -90, opacity: 0 }}
          animate={prefersReducedMotion ? false : { rotate: 0, opacity: 1 }}
          transition={{ duration: 0.4, delay: 0.1 }}
          className="w-9 h-9 rounded-full bg-primary/10 border border-primary/30 flex items-center justify-center text-primary shrink-0"
        >
          <Lock className="w-5 h-5" aria-hidden="true" />
        </motion.div>
        <div>
          <p className="text-xs font-mono fc-text-muted uppercase tracking-wider">Status: Secured</p>
          <h2
            ref={headingRef}
            tabIndex={-1}
            className="text-lg font-heading font-bold fc-text-primary outline-none"
          >
            Evidence Sealed
          </h2>
        </div>
      </div>

      {/* ── File preview card ── */}
      <div className="bg-white/[0.03] border border-white/10 rounded-xl overflow-hidden mb-5">

        {/* Preview area — varies by file category */}
        <div className="relative overflow-hidden bg-black/30 border-b border-white/5 min-h-[160px] max-h-[220px] flex items-center justify-center">
          <motion.div
            className="absolute inset-0 flex flex-col items-center justify-center"
            initial={prefersReducedMotion ? false : { scale: 0.9, opacity: 0, filter: "blur(4px)" }}
            animate={prefersReducedMotion ? false : { scale: 1, opacity: 1, filter: "blur(0px)" }}
            transition={SPRING_GENTLE}
          >
            {fileCategory === "image" && objectUrl ? (
              <>
                <Image
                  src={objectUrl}
                  alt={`Evidence file preview: ${file.name}`}
                  fill
                  sizes="(max-width: 640px) 100vw, 576px"
                  unoptimized
                  className="object-cover"
                />
                {/* Scan line animation — reduced-motion gated */}
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
              <FileCategoryIcon category={fileCategory} extension={extension} />
            )}
          </motion.div>
        </div>

        {/* File metadata */}
        <div className="p-4 flex flex-col gap-2">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span
              className="text-sm font-semibold fc-text-primary truncate max-w-[65%]"
              title={file.name}
            >
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

          {/* SHA-256 hash */}
          <div className="pt-2 border-t border-white/5 flex flex-col gap-1">
            <span className="text-xs font-mono fc-text-muted uppercase tracking-wider">
              SHA-256 Checksum
            </span>
            {/* aria-live so screen readers announce hash completion */}
            <span
              aria-live="polite"
              aria-atomic="true"
              className="text-xs font-mono text-primary truncate flex items-center gap-2"
              title={fileSha256 ?? undefined}
            >
              {isHashComputing ? (
                <>
                  <span
                    className="w-3 h-3 rounded-full border border-primary border-t-transparent animate-spin shrink-0"
                    aria-hidden="true"
                  />
                  <span className="text-primary/60">Calculating SHA-256...</span>
                </>
              ) : hashError ? (
                <span className="text-red-400">Hash unavailable — reselect file</span>
              ) : fileSha256 ? (
                `${fileSha256.slice(0, 24).toLowerCase()}...${fileSha256.slice(-12).toLowerCase()}`
              ) : (
                <span className="text-primary/60">Waiting...</span>
              )}
            </span>
          </div>
        </div>
      </div>

      {/* Auth error */}
      {authError && (
        <div
          className="mb-5 p-4 rounded-xl border border-danger/20 bg-danger/5 text-sm fc-text-danger relative z-10"
          role="alert"
        >
          <strong>Authentication Error:</strong> {authError}. Please close the modal and try again.
        </div>
      )}

      {/* ── Action buttons ── */}
      <div className="flex gap-3 relative z-10">
        <button
          type="button"
          onClick={closeModal}
          className="fc-btn-secondary flex-1 text-sm"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={onStartAnalysis}
          disabled={isHandingOff || isHashComputing || !!hashError || !fileSha256}
          aria-label={
            isHashComputing
              ? "Deploy Council — waiting for hash computation"
              : isHandingOff
              ? "Initializing agents, please wait"
              : "Deploy Council forensic agents"
          }
          data-testid="upload-start-analysis"
          className="fc-btn-primary flex-[2] group relative overflow-hidden text-sm"
        >
          <span className="relative z-10 flex items-center justify-center gap-2">
            {isHandingOff ? (
              <>
                <span
                  className="w-3.5 h-3.5 rounded-full border-2 border-current border-t-transparent animate-spin"
                  aria-hidden="true"
                />
                Initializing Agents...
              </>
            ) : isHashComputing ? (
              <>
                <span
                  className="w-3.5 h-3.5 rounded-full border-2 border-current border-t-transparent animate-spin"
                  aria-hidden="true"
                />
                Computing Hash...
              </>
            ) : (
              <>
                Deploy Council
                <ArrowRight
                  className="w-4 h-4 group-hover:translate-x-1 transition-transform"
                  aria-hidden="true"
                />
              </>
            )}
          </span>
          {/* Hover shimmer */}
          <div
            className="absolute inset-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300 ease-out"
            aria-hidden="true"
          />
        </button>
      </div>
    </motion.div>
  );
}

/** Icon block displayed in the preview area for non-image file types. */
function FileCategoryIcon({
  category,
  extension,
}: {
  category: "image" | "audio" | "video" | "document" | "unknown";
  extension: string;
}) {
  const configs = {
    image: {
      Icon: ImageFileIcon,
      label: "Image Evidence",
      gradient: "from-primary/20 to-primary/10",
      border: "border-primary/30",
      color: "text-primary",
    },
    audio: {
      Icon: Music,
      label: "Audio Evidence",
      gradient: "from-teal-500/20 to-teal-500/10",
      border: "border-teal-500/30",
      color: "text-teal-400",
    },
    video: {
      Icon: Video,
      label: "Video Evidence",
      gradient: "from-violet-500/20 to-violet-500/10",
      border: "border-violet-500/30",
      color: "text-violet-400",
    },
    document: {
      Icon: FileText,
      label: "Document Evidence",
      gradient: "from-amber-500/20 to-amber-500/10",
      border: "border-amber-500/30",
      color: "text-amber-400",
    },
    unknown: {
      Icon: ImageFileIcon,
      label: "Evidence File",
      gradient: "from-white/10 to-white/5",
      border: "border-white/20",
      color: "fc-text-muted",
    },
  } as const;

  const cfg = configs[category] ?? configs.unknown;
  const { Icon, label, gradient, border, color } = cfg;

  return (
    <div className="flex flex-col items-center justify-center p-6 text-center gap-3">
      <div
        className={`w-16 h-16 rounded-2xl bg-gradient-to-br ${gradient} border ${border} ${color} flex items-center justify-center`}
      >
        <Icon className="w-8 h-8" aria-hidden="true" />
      </div>
      <div>
        <span className={`text-xs font-mono uppercase tracking-wider ${color}`}>
          {label}
        </span>
        {extension && (
          <p className="text-xs fc-text-muted mt-0.5">{extension.toUpperCase()} file</p>
        )}
      </div>
    </div>
  );
}
