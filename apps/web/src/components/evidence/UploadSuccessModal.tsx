"use client";

import { useCallback, useState, useEffect, useRef } from "react";
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
import { TRANSITION_ENTER } from "@/lib/animations";

export interface UploadSuccessModalProps {
  file: File;
  fileSha256: string | null;
  hashError?: string | null;
  isHashComputing?: boolean;
  onStartAnalysis: () => Promise<void> | void;
  /** Return to the file picker (UploadModal) keeping the dialog open. */
  onDismiss: () => void;
  /** Close the entire dialog. When omitted, Cancel falls back to onDismiss. */
  onCancel?: () => void;
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
  onCancel,
  isHandingOff = false,
  authError,
}: UploadSuccessModalProps) {
  const { playSound } = useSound();
  const prefersReducedMotion = useReducedMotion();
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState(false);
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

  // FLOW: "Reselect" returns to the picker (onDismiss); "Cancel" closes the
  // whole dialog (onCancel). Previously both invoked onDismiss, so Cancel
  // confusingly re-opened the picker instead of dismissing the flow.
  const reselectFile = useCallback(() => {
    playSound("click");
    onDismiss();
  }, [playSound, onDismiss]);

  const cancelFlow = useCallback(() => {
    playSound("envelope-close");
    (onCancel ?? onDismiss)();
  }, [playSound, onCancel, onDismiss]);

  return (
    <motion.div
      key="success-state"
      // §6: opacity + subtle Y only — no scale/blur entrances.
      initial={prefersReducedMotion ? false : { opacity: 0, y: 8 }}
      animate={prefersReducedMotion ? false : { opacity: 1, y: 0 }}
      exit={prefersReducedMotion ? {} : { opacity: 0, y: -4 }}
      transition={TRANSITION_ENTER}
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
        onClick={reselectFile}
        aria-label="Reselect a different file"
        data-testid="success-modal-close"
        className="absolute top-4 right-4 z-20 inline-flex items-center gap-1.5 h-9 px-3 min-w-[44px] rounded-full text-xs font-medium fc-text-muted hover:text-foreground hover:bg-white/5 border border-transparent hover:border-white/10 fc-transition fc-focus-ring cursor-pointer"
      >
        <ArrowLeft className="w-3.5 h-3.5" aria-hidden="true" />
        <span>Reselect</span>
      </button>

      {/* ── Status header ── */}
      <div className="mb-5 flex items-center gap-3 relative z-10">
        <motion.div
          initial={prefersReducedMotion ? false : { opacity: 0 }}
          animate={prefersReducedMotion ? false : { opacity: 1 }}
          transition={{ duration: 0.16, delay: 0.05 }}
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
        <div className="relative overflow-hidden bg-surface-1 border-b border-white/5 min-h-[160px] max-h-[220px] flex items-center justify-center">
          <motion.div
            className="absolute inset-0 flex flex-col items-center justify-center"
            initial={prefersReducedMotion ? false : { opacity: 0 }}
            animate={prefersReducedMotion ? false : { opacity: 1 }}
            transition={TRANSITION_ENTER}
          >
            {fileCategory === "image" && objectUrl && !previewError ? (
              <>
                {/* Plain <img> (not next/image) renders blob: object URLs
                    reliably without the optimizer; object-contain shows the
                    whole evidence frame. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={objectUrl}
                  alt={`Evidence file preview: ${file.name}`}
                  onError={() => setPreviewError(true)}
                  className="absolute inset-0 w-full h-full object-contain"
                  decoding="async"
                />
                {/* Seal glint — one-shot opacity fade over the preview confirms
                    capture (§6: scan-beam sweeps and colored shadows are banned) */}
                {!prefersReducedMotion && (
                  <motion.div
                    initial={{ opacity: 0.22 }}
                    animate={{ opacity: 0 }}
                    transition={{ duration: 0.2, ease: "easeOut" }}
                    className="absolute inset-0 pointer-events-none z-10"
                    style={{
                      background:
                        "linear-gradient(180deg, rgba(255,255,255,0.5), transparent 60%)",
                    }}
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
                <span className="fc-text-danger">Hash unavailable — reselect file</span>
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
          onClick={cancelFlow}
          aria-label="Cancel and close the upload dialog"
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
                  className="w-4 h-4 group-hover:translate-x-1 transition-transform duration-150"
                  aria-hidden="true"
                />
              </>
            )}
          </span>
          {/* Hover treatment comes from fc-btn-primary itself — the previous
              white-wash slide-in overlay fought the button system's hover state
              and used a non-canonical 300ms transform. */}
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
  // Evidence-type hues come from the agent accent token palette (globals.css)
  // so a file type previews in the SAME color its analyzing agent uses across
  // live progress and the report. Raw teal/violet/amber Tailwind hues are out:
  // amber especially collided with the semantic warning color. Every class
  // literal below is also declared in agentTheme.ts, so Tailwind's scanner
  // has already generated them.
  const configs = {
    image: {
      Icon: ImageFileIcon,
      label: "Image Evidence",
      bg: "bg-[var(--color-agent-image)]/10",
      border: "border-[var(--color-agent-image)]/30",
      color: "text-[var(--color-agent-image)]",
    },
    audio: {
      Icon: Music,
      label: "Audio Evidence",
      bg: "bg-[var(--color-agent-audio)]/10",
      border: "border-[var(--color-agent-audio)]/30",
      color: "text-[var(--color-agent-audio)]",
    },
    video: {
      Icon: Video,
      label: "Video Evidence",
      bg: "bg-[var(--color-agent-video)]/10",
      border: "border-[var(--color-agent-video)]/30",
      color: "text-[var(--color-agent-video)]",
    },
    document: {
      Icon: FileText,
      label: "Document Evidence",
      bg: "bg-[var(--color-agent-metadata)]/10",
      border: "border-[var(--color-agent-metadata)]/30",
      color: "text-[var(--color-agent-metadata)]",
    },
    unknown: {
      Icon: ImageFileIcon,
      label: "Evidence File",
      bg: "bg-white/5",
      border: "border-white/20",
      color: "fc-text-muted",
    },
  } as const;

  const cfg = configs[category] ?? configs.unknown;
  const { Icon, label, bg, border, color } = cfg;

  return (
    <div className="flex flex-col items-center justify-center p-6 text-center gap-3">
      <div
        className={`w-16 h-16 rounded-2xl ${bg} border ${border} ${color} flex items-center justify-center`}
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
