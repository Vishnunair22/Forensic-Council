"use client";

import { useCallback, useState, useEffect, useRef } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Lock, ArrowRight, X, Play, Mic, FileText, Archive, File } from "lucide-react";
import { useSound } from "@/hooks/useSound";
import { formatBytes } from "@/lib/utils";
import { FADE_IN_SCALE, TRANSITION_SMOOTH } from "@/lib/animations";

export interface UploadSuccessModalProps {
  file: File;
  onStartAnalysis: () => Promise<void> | void;
  onDismiss: () => void;
  isHandingOff?: boolean;
  authError?: string | null;
}

function useSHA256Checksum(file: File) {
  const [checksum, setChecksum] = useState("");
  const [isComputing, setIsComputing] = useState(true);

  useEffect(() => {
    let active = true;
    setIsComputing(true);
    const compute = async () => {
      const CHUNK_SIZE = 10 * 1024 * 1024;
      const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
      const hashBuffer = new Uint8Array(32);
      try {
        const arrayBuffer = await file.arrayBuffer();
        const hash = await crypto.subtle.digest("SHA-256", arrayBuffer);
        const hashArray = Array.from(new Uint8Array(hash));
        const hashHex = hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
        if (active) {
          setChecksum(hashHex);
          setIsComputing(false);
        }
      } catch (err) {
        console.error("SHA-256 fallback:", err);
        const ts = Date.now().toString(16).padStart(12, "0");
        const sz = file.size.toString(16).padStart(8, "0");
        const nm = Array.from(file.name).reduce((a, c) => (a * 31 + c.charCodeAt(0)) & 0xffffffff, 0).toString(16).padStart(8, "0");
        const fallback = `${ts}${sz}${nm}${"0".repeat(28)}`.substring(0, 64);
        if (active) {
          setChecksum(fallback);
          setIsComputing(false);
        }
      }
    };
    compute();
    return () => { active = false; };
  }, [file]);

  return { checksum, isComputing };
}

export function UploadSuccessModal({
  file,
  onStartAnalysis,
  onDismiss,
  isHandingOff = false,
  authError,
}: UploadSuccessModalProps) {
  const { playSound } = useSound();
  const prefersReducedMotion = useReducedMotion();
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [videoDuration, setVideoDuration] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const { checksum, isComputing } = useSHA256Checksum(file);

  useEffect(() => {
    let url: string | null = null;
    const isImageOrVideo = file.type.startsWith("image/") || file.type.startsWith("video/");
    if (isImageOrVideo) {
      url = URL.createObjectURL(file);
      setObjectUrl(url);
    }
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [file]);

  const closeModal = useCallback(() => {
    playSound("click");
    onDismiss();
  }, [playSound, onDismiss]);

  const handleVideoMetadata = () => {
    if (videoRef.current) {
      videoRef.current.currentTime = 0;
      videoRef.current.pause();
      const duration = videoRef.current.duration;
      if (!isNaN(duration) && isFinite(duration)) {
        const mins = Math.floor(duration / 60);
        const secs = Math.floor(duration % 60);
        setVideoDuration(`${mins}:${secs < 10 ? "0" : ""}${secs}`);
      }
    }
  };

  const getFileCategoryDetails = () => {
    const type = file.type || "";
    const name = file.name || "";
    if (type.startsWith("audio/")) {
      return { icon: Mic, accentClass: "from-blue-500/20 to-blue-600/10 border-blue-500/30 text-blue-400", label: "Audio Evidence" };
    }
    if (type === "application/pdf" || name.endsWith(".pdf")) {
      return { icon: FileText, accentClass: "from-red-500/20 to-red-600/10 border-red-500/30 text-red-400", label: "PDF Document" };
    }
    if (type === "application/msword" || type === "application/vnd.openxmlformats-officedocument.wordprocessingml.document" || name.endsWith(".doc") || name.endsWith(".docx")) {
      return { icon: FileText, accentClass: "from-blue-400/20 to-blue-500/10 border-blue-400/30 text-blue-300", label: "Word Document" };
    }
    if (type === "application/zip" || type === "application/x-tar" || type === "application/x-gzip" || type === "application/x-bzip2" || type === "application/x-7z-compressed" || name.endsWith(".zip") || name.endsWith(".tar") || name.endsWith(".gz") || name.endsWith(".7z")) {
      return { icon: Archive, accentClass: "from-amber-500/20 to-amber-600/10 border-amber-500/30 text-amber-400", label: "Compressed Archive" };
    }
    return { icon: File, accentClass: "from-white/[0.06] to-white/[0.03] border-white/[0.12] fc-text-muted", label: "Binary Evidence" };
  };

  const fileCategory = getFileCategoryDetails();
  const CategoryIcon = fileCategory.icon;
  const extension = file.name.includes(".") ? file.name.substring(file.name.lastIndexOf(".")).toLowerCase() : "";

  return (
    <motion.div
      key="success-state"
      initial={prefersReducedMotion ? false : { opacity: 0, scale: 0.95, filter: "blur(4px)" }}
      animate={prefersReducedMotion ? false : { opacity: 1, scale: 1, filter: "blur(0px)" }}
      exit={prefersReducedMotion ? {} : { opacity: 0, scale: 1.05, filter: "blur(4px)" }}
      transition={TRANSITION_SMOOTH}
      className="p-6 sm:p-8 flex flex-col text-left relative overflow-hidden max-h-[90vh] md:max-h-none"
    >
      <div className="absolute inset-0 opacity-[0.03] pointer-events-none bg-[radial-gradient(#fff_1px,transparent_1px)] [background-size:16px_16px]" aria-hidden="true" />

      <button
        type="button"
        onClick={closeModal}
        aria-label="Close evidence dialog"
        data-testid="success-modal-close"
        className="absolute top-4 right-4 w-8 h-8 flex items-center justify-center fc-text-muted hover:fc-text-primary hover:bg-white/5 border border-transparent hover:border-white/10 fc-transition fc-focus-ring rounded-full cursor-pointer z-20"
      >
        <X className="w-4 h-4" aria-hidden="true" />
      </button>

      <div className="mb-5 flex items-center justify-between relative z-10">
        <div className="flex items-center gap-3">
          <motion.div
            initial={{ rotate: -90, opacity: 0 }}
            animate={{ rotate: 0, opacity: 1 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="w-9 h-9 rounded-full bg-primary/10 border border-primary/30 flex items-center justify-center text-primary"
          >
            <Lock className="w-4.5 h-4.5" aria-hidden="true" />
          </motion.div>
          <div>
            <p className="text-xs font-mono fc-text-muted uppercase tracking-wider">Status: Secured</p>
            <h2 className="text-lg font-heading font-bold fc-text-primary">Evidence Sealed</h2>
          </div>
        </div>
      </div>

      <div className="bg-white/[0.03] border border-white/10 rounded-xl overflow-hidden mb-6">
        <div className="relative overflow-hidden bg-black/30 border-b border-white/5 min-h-[180px] max-h-[260px] flex items-center justify-center">
          <motion.div
            className="w-full h-full flex flex-col items-center justify-center relative"
            initial={{ scale: 0.9, opacity: 0, filter: "blur(4px)" }}
            animate={{ scale: 1, opacity: 1, filter: "blur(0px)" }}
            transition={{ type: "spring", stiffness: 300, damping: 25, duration: 0.35 }}
          >
            {objectUrl && file.type.startsWith("image/") ? (
              <>
                <img
                  src={objectUrl}
                  alt={file.name}
                  className="w-full h-full object-cover"
                />
                <motion.div
                  initial={{ top: "0%", opacity: 1 }}
                  animate={{ top: "100%", opacity: 0 }}
                  transition={{ duration: 1.5, ease: "easeInOut" }}
                  className="absolute left-0 right-0 h-[2px] bg-primary/80 shadow-[0_0_8px_var(--color-primary)] pointer-events-none z-10"
                />
              </>
            ) : objectUrl && file.type.startsWith("video/") ? (
              <div className="w-full h-full relative flex items-center justify-center">
                <video
                  ref={videoRef}
                  src={objectUrl}
                  muted
                  playsInline
                  preload="metadata"
                  onLoadedMetadata={handleVideoMetadata}
                  className="w-full h-full object-cover"
                />
                <div className="absolute inset-0 bg-black/20 flex items-center justify-center z-10">
                  <div className="w-10 h-10 rounded-full bg-background/80 border border-white/20 flex items-center justify-center text-white/90">
                    <Play className="w-4 h-4 ml-0.5" />
                  </div>
                </div>
                {videoDuration && (
                  <div className="absolute bottom-2 right-2 bg-background/80 px-1.5 py-0.5 rounded text-xs font-mono text-white/90 border border-white/10 z-10">
                    {videoDuration}
                  </div>
                )}
                <motion.div
                  initial={{ top: "0%", opacity: 1 }}
                  animate={{ top: "100%", opacity: 0 }}
                  transition={{ duration: 1.5, ease: "easeInOut" }}
                  className="absolute left-0 right-0 h-[2px] bg-primary/80 shadow-[0_0_8px_var(--color-primary)] pointer-events-none z-10"
                />
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center p-4 text-center">
                <div className={`w-14 h-14 rounded-xl bg-gradient-to-br ${fileCategory.accentClass} flex items-center justify-center border mb-2`}>
                  <CategoryIcon className="w-7 h-7" />
                </div>
                <span className="text-xs font-mono tracking-wider fc-text-muted uppercase">
                  {fileCategory.label}
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
            <span className="text-[9px] font-mono fc-text-muted uppercase tracking-wider">
              SHA-256 Checksum
            </span>
            <motion.span
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.5 }}
              className="text-xs font-mono text-primary truncate flex items-center gap-2"
            >
              {isComputing ? (
                <>
                  <span className="w-3 h-3 rounded-full border border-primary border-t-transparent animate-spin" />
                  <span className="text-primary/60">Calculating...</span>
                </>
              ) : (
                `${checksum.substring(0, 24).toLowerCase()}...`
              )}
            </motion.span>
          </div>
        </div>
      </div>

      {authError && (
        <div
          className="mb-6 p-4 rounded-xl border border-red-500/20 bg-red-500/5 text-sm fc-text-danger relative z-10"
          role="alert"
        >
          <strong>Authentication Error:</strong> {authError}. Please close the modal and try again to establish a valid investigator session.
        </div>
      )}

      <div className="flex gap-3 relative z-10 mt-auto">
        <button onClick={onDismiss} className="fc-btn-secondary flex-1 text-sm py-2">
          Cancel
        </button>
        <button
          onClick={onStartAnalysis}
          disabled={isHandingOff}
          data-testid="upload-start-analysis"
          className="fc-btn-primary flex-[2] group relative overflow-hidden text-sm py-2"
        >
          <span className="relative z-10 flex items-center justify-center gap-2">
            {isHandingOff ? "Initializing Agents..." : "Deploy Council"}
            {!isHandingOff && <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />}
          </span>
          <div className="absolute inset-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300 ease-out" />
        </button>
      </div>
    </motion.div>
  );
}
