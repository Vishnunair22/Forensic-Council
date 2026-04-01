/**
 * AgentProgressDisplay Component
 * ================================
 * Shows agent cards in a grid with real-time status, expandable findings,
 * and decision buttons after each analysis phase.
 */

import React from "react";
import { clsx } from "clsx";
import {
  CheckCircle2, Loader2, ArrowRight,
  RotateCcw, Microscope, FileText, ChevronDown, ChevronUp,
} from "lucide-react";
import { AgentIcon } from "@/components/ui/AgentIcon";
import { Badge } from "@/components/lightswind/badge";
import AnimatedWave from "@/components/lightswind/animated-wave";
import { AGENTS_DATA } from "@/lib/constants";
import { useState, useEffect, useRef } from "react";
import { SoundType } from "@/hooks/useSound";
import { fmtTool } from "@/lib/fmtTool";

export interface SectionFlag {
  id: string;
  label: string;
  flag: "ok" | "warn" | "bad" | "info";
  key_signal: string;
}

export interface FindingPreview {
  tool: string;
  summary: string;
  confidence: number;
  flag: "ok" | "warn" | "bad" | "info";
  severity: string;
  verdict: "CLEAN" | "FLAGGED" | "NOT_APPLICABLE" | "ERROR";
  key_signal: string;
  section: string;
}

export interface AgentUpdate {
  agent_id: string;
  agent_name: string;
  message: string;
  status: "running" | "complete" | "error" | "skipped";
  confidence?: number;
  findings_count?: number;
  thinking?: string;
  error?: string | null;
  deep_analysis_pending?: boolean;
  /** Groq-synthesized overall verdict for this agent */
  agent_verdict?: "AUTHENTIC" | "LIKELY_MANIPULATED" | "INCONCLUSIVE" | null;
  /** Tool error / fallback rate (0–1) */
  tool_error_rate?: number;
  /** Per-section flags produced by grouped Groq synthesis */
  section_flags?: SectionFlag[];
  /** Per-finding preview list (always available, no Groq required) */
  findings_preview?: FindingPreview[];
  /** Count of tools that ran successfully */
  tools_ran?: number;
  /** Count of tools that returned NOT_APPLICABLE (wrong file type) */
  tools_skipped?: number;
  /** Count of tools that failed (court_defensible=false) */
  tools_failed?: number;
}

interface AgentProgressDisplayProps {
  agentUpdates: Record<string, { status: string; thinking: string; tools_done?: number; tools_total?: number }>;
  completedAgents: AgentUpdate[];
  progressText: string;
  allAgentsDone: boolean;
  phase: "initial" | "deep";
  awaitingDecision: boolean;
  pipelineStatus?: string;
  pipelineMessage?: string;
  onAcceptAnalysis?: () => void;
  onDeepAnalysis?: () => void;
  onNewUpload?: () => void;
  onViewResults?: () => void;
  playSound?: (type: SoundType) => void;
  isNavigating?: boolean;
}

// ── Per-card expandable text ──────────────────────────────────────────────────
const TRUNCATE_CHARS = 500;

function truncateAtWord(text: string, maxChars: number): string {
  if (text.length <= maxChars) return text;
  // Find last space at or before maxChars
  const sub = text.slice(0, maxChars);
  const lastSpace = sub.lastIndexOf(" ");
  return lastSpace > maxChars * 0.6
    ? sub.slice(0, lastSpace)
    : sub; // no good word boundary found, use raw slice
}

function ExpandableText({
  text,
  textClassName,
  wrapperClassName,
}: {
  text: string;
  textClassName?: string;
  wrapperClassName?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const needsTruncation = text.length > TRUNCATE_CHARS;
  const displayText = needsTruncation && !expanded
    ? truncateAtWord(text, TRUNCATE_CHARS) + "…"
    : text;

  return (
    <div className={wrapperClassName}>
      <p className={`text-xs leading-relaxed whitespace-pre-wrap break-words ${textClassName || "text-slate-300"}`}>
        {displayText}
      </p>
      {needsTruncation && (
        <button
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className="inline-flex items-center gap-0.5 mt-1.5 text-[11px] font-bold transition-colors uppercase tracking-widest"
          style={{ color: "rgba(34,211,238,0.65)" }}
        >
          {expanded ? (
            <><ChevronUp className="w-3.5 h-3.5" aria-hidden="true" />Show less</>
          ) : (
            <><ChevronDown className="w-3.5 h-3.5" aria-hidden="true" />Show more</>
          )}
        </button>
      )}
    </div>
  );
}

// ── Findings accordion ───────────────────────────────────────────────────────
const FLAG_STYLES = {
  ok:   { dot: "bg-emerald-500",  text: "text-emerald-400", bar: "bg-emerald-500/20", icon: "✓" },
  ok_alt: { dot: "bg-amber-500", text: "text-amber-400", bar: "bg-amber-500/20", icon: "·" },
  warn: { dot: "bg-amber-500",    text: "text-amber-400",   bar: "bg-amber-500/20",   icon: "⚠" },
  bad:  { dot: "bg-rose-500",      text: "text-rose-400",     bar: "bg-rose-500/20",     icon: "✕" },
  info: { dot: "bg-white/40",    text: "text-white/40",   bar: "bg-white/5",   icon: "·" },
} as const;

function FindingsAccordion({
  sectionFlags,
  findingsCount,
}: {
  sectionFlags: SectionFlag[];
  findingsCount?: number;
}) {
  const [open, setOpen] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  return (
    <div className="rounded-xl border border-white/5 glass-panel overflow-hidden shadow-sm mt-2">
      {/* ── Accordion header ── */}
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={open ? "Collapse findings" : "Expand findings"}
        className="w-full flex items-center justify-between px-4 py-3
          hover:bg-white/[0.05] transition-colors group"
      >
        <div className="flex items-center gap-3">
          {/* Mini flag dots summary */}
          <div className="flex gap-1.5">
            {sectionFlags.map((sf) => (
              <span
                key={sf.id}
                className={`w-1.5 h-1.5 rounded-full shadow-[0_0_5px_rgba(0,0,0,0.5)] ${FLAG_STYLES[sf.flag]?.dot ?? "bg-slate-500"}`}
              />
            ))}
          </div>
          <span className="text-[10px] font-bold tracking-widest uppercase font-mono text-foreground/40">
            {findingsCount ?? sectionFlags.length} Artifact{(findingsCount ?? sectionFlags.length) !== 1 ? "s" : ""}
          </span>
        </div>
        <span aria-hidden="true" className="text-white/20 group-hover:text-cyan-400 transition-colors">
          <ChevronDown className={`w-4 h-4 transition-transform ${open ? "rotate-180" : ""}`} />
        </span>
      </button>

      {/* ── Expandable section list ── */}
      {open && (
          <div
            key="findings-body"
            
            
            
            
            className="overflow-hidden"
          >
            <div style={{ borderTop: "1px solid rgba(255,255,255,0.03)", background: "rgba(0,0,0,0.1)" }}>
              {sectionFlags.map((sf) => {
                const style  = FLAG_STYLES[sf.flag] ?? FLAG_STYLES.info;
                const isExp  = expandedId === sf.id;
                const hasDetail = !!sf.key_signal;

                return (
                  <div key={sf.id}>
                    <button
                      onClick={() => hasDetail && setExpandedId(isExp ? null : sf.id)}
                      disabled={!hasDetail}
                      aria-expanded={hasDetail ? isExp : undefined}
                      aria-label={hasDetail ? (isExp ? `Collapse ${sf.label}` : `Expand ${sf.label}`) : sf.label}
                      className={[
                        "w-full flex items-center gap-3 px-3.5 py-2.5 transition-colors",
                        hasDetail
                          ? "hover:bg-white/[0.04] cursor-pointer group"
                          : "cursor-default",
                      ].join(" ")}
                    >
                      {/* Color bar */}
                      <span className={`w-[2px] h-3.5 rounded-full flex-shrink-0 ${style.bar}`} />
                      {/* Flag icon */}
                      <span className={`text-[12px] font-black flex-shrink-0 w-5 text-center drop-shadow-md ${style.text}`}>
                        {style.icon}
                      </span>
                      {/* Section label */}
                      <span className={`text-xs font-medium flex-1 text-left tracking-wide ${style.text}`}>
                        {sf.label}
                      </span>
                      {hasDetail && (
                        <span
                          
                          
                          className="text-white/20 group-hover:text-cyan-400/70 transition-colors flex-shrink-0"
                        >
                          <ChevronDown className="w-3.5 h-3.5" />
                        </span>
                      )}
                    </button>

                    {/* ── Section key signal detail ── */}
                    {isExp && sf.key_signal && (
                        <div
                          key={`detail-${sf.id}`}
                          className="overflow-hidden"
                          style={{ background: "rgba(0,0,0,0.15)" }}
                        >
                          <p className="px-10 pb-3 pt-1 text-[11px] text-foreground/60 font-mono leading-relaxed border-l border-border-bold ml-4">
                            {sf.key_signal}
                          </p>
                        </div>
                      )}
                    </div>
                );
              })}
            </div>
          </div>
        )}
    </div>
  );
}

// ── Per-finding preview list ─────────────────────────────────────────────────

const SEV_BORDER: Record<string, string> = {
  CRITICAL: "border-l-red-500",
  HIGH:     "border-l-red-400",
  MEDIUM:   "border-l-amber-400",
  LOW:      "border-l-slate-600/80",
  INFO:     "border-l-slate-700",
};

const SEV_LABEL: Record<string, { text: string; variant: "destructive" | "warning" | "default" | "secondary" | "success" | "info" | "outline" }> = {
  CRITICAL: { text: "CRITICAL", variant: "destructive" },
  HIGH:     { text: "HIGH",     variant: "destructive" },
  MEDIUM:   { text: "MEDIUM",   variant: "warning" },
  LOW:      { text: "LOW",      variant: "secondary" },
  INFO:     { text: "INFO",     variant: "outline" },
};

const CLAMP_CHARS = 150;

function FindingRow({ f }: { f: FindingPreview }) {
  const [open, setOpen] = useState(false);
  // Strip "Tool Name: " prefix — _build_readable_summary prefixes with the tool
  // label (e.g. "File Hash Verify: ...") but the heading already shows the tool name.
  const cleanSummary = (() => {
    const heading = f.tool.replace(/_/g, " ").trim().toLowerCase();
    const s = f.summary.trimStart();
    const colonIdx = s.indexOf(":");
    if (colonIdx > 0 && colonIdx < 60) {
      const prefix = s.slice(0, colonIdx).toLowerCase().replace(/\s+/g, " ").trim();
      if (prefix === heading || heading.includes(prefix) || prefix.includes(heading)) {
        return s.slice(colonIdx + 1).trimStart();
      }
    }
    return s;
  })();
  const needsExpand = cleanSummary.length > CLAMP_CHARS;
  const displayText = needsExpand && !open
    ? cleanSummary.slice(0, CLAMP_CHARS).trimEnd() + "…"
    : cleanSummary;
  const borderCls = SEV_BORDER[f.severity] ?? SEV_BORDER.LOW;
  const sev = SEV_LABEL[f.severity] ?? SEV_LABEL.LOW;

  const verdictCls = f.verdict === "CLEAN" ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/20"
    : f.verdict === "FLAGGED" ? "text-red-400 bg-red-500/10 border-red-500/20"
    : f.verdict === "NOT_APPLICABLE" ? "text-slate-500 bg-slate-500/10 border-slate-500/20"
    : "text-amber-400 bg-amber-500/10 border-amber-500/20";
  const verdictLabel = f.verdict === "NOT_APPLICABLE" ? "N/A" : f.verdict;

  return (
    <div 
      className={`rounded-xl glass-panel overflow-hidden border border-border-subtle border-l-2 ${borderCls} px-4 py-3 space-y-2 shadow-sm group/finding`}
    >
      {/* Header: tool name + severity + confidence + per-tool verdict */}
      <div className="flex items-start gap-3">
        <span className="text-[10px] font-black tracking-[0.2em] uppercase flex-1 leading-tight font-mono" style={{ color: "rgba(34,211,238,0.8)" }}>
          {fmtTool(f.tool)}
        </span>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className={`text-[8px] font-mono font-bold px-1.5 py-0.5 rounded border ${verdictCls} uppercase tracking-wider`}>
            {verdictLabel}
          </span>
          {f.severity !== "LOW" && f.severity !== "INFO" && (
            <Badge variant={sev.variant} size="sm" shape="rounded" className="font-black tracking-widest px-1.5">
              {sev.text}
            </Badge>
          )}
          {f.confidence > 0.15 && f.verdict !== "NOT_APPLICABLE" && (
            <span className="text-[9px] font-mono font-bold text-slate-300 bg-white/5 border border-white/10 px-1.5 py-0.5 rounded shadow-inner uppercase tracking-tighter">
              {Math.round(f.confidence * 100)}% conf
            </span>
          )}
        </div>
      </div>
      {/* Summary */}
      <p className="text-[11px] text-slate-300 leading-relaxed max-w-prose font-medium">
        {displayText}
        {needsExpand && (
          <button
            onClick={() => setOpen(v => !v)}
            className="ml-2 text-[9px] font-black uppercase tracking-[0.2em] transition-colors" style={{ color: "rgba(34,211,238,0.55)" }}
          >
            [{open ? "COLLAPSE" : "EXPAND"}]
          </button>
        )}
      </p>
      {/* Groq key signal (if available and different from summary) */}
      {f.key_signal && f.key_signal !== cleanSummary && (
        <p className="text-[10px] text-cyan-400/50 font-mono leading-relaxed pl-2 border-l border-cyan-500/20">
          {f.key_signal}
        </p>
      )}
    </div>
  );
}

function FindingsPreviewList({ findings }: { findings: FindingPreview[] }) {
  const [showAll, setShowAll] = useState(false);
  const INITIAL_SHOW = 2; 
  const firstBatch = findings.slice(0, INITIAL_SHOW);
  const remainingBatch = findings.slice(INITIAL_SHOW);
  const remaining = remainingBatch.length;

  return (
    <div  className="space-y-2">
      {firstBatch.map((f, i) => <FindingRow key={`${f.tool}-first-${i}`} f={f} />)}
      
      {findings.length > INITIAL_SHOW && (
        <button
          
          onClick={() => setShowAll(v => !v)}
          className="w-full text-[9px] font-black tracking-[0.2em] uppercase text-white/30 hover:text-cyan-400 transition-all py-2 text-center
            border border-white/5 border-dashed rounded glass-panel hover:bg-white/5 my-1"
        >
          {showAll
            ? "Hide Suppressed Findings"
            : `Display ${remaining} Suppressed Finding${remaining !== 1 ? "s" : ""}`}
        </button>
      )}

      {showAll && remainingBatch.map((f, i) => <FindingRow key={`${f.tool}-rem-${i}`} f={f} />)}
    </div>
  );
}

// ── Live animated thinking text ──────────────────────────────────────────────
/**
 * Shows the current thinking text with smooth animated transitions.
 * Text changes trigger a blur-fade-out → slide-up-fade-in transition,
 * giving a "real-time reasoning" feel. Previous thought lingers dimly
 * for one cycle as a trail.
 */
function LiveThinkingText({ text, active }: { text: string; active: boolean }) {
  // Debounce text changes to avoid flicker from rapid 200ms heartbeat updates
  const [displayText, setDisplayText] = useState(text);
  const [prevText, setPrevText] = useState<string | null>(null);
  const [key, setKey] = useState(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const trailTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Animated dots for long-running tasks
  const [dotCount, setDotCount] = useState(1);

  useEffect(() => {
    if (text === displayText) return;

    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setPrevText(displayText);
      setDisplayText(text);
      setKey(k => k + 1);

      // Clear the trail after it fades out
      if (trailTimerRef.current) clearTimeout(trailTimerRef.current);
      trailTimerRef.current = setTimeout(() => setPrevText(null), 1800);
    }, 150);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);

  // Animate dots while active
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setDotCount(c => (c % 3) + 1), 600);
    return () => clearInterval(id);
  }, [active]);

  const dots = active ? ".".repeat(dotCount) : "";

  return (
    <div className="relative space-y-1 min-h-[2.5rem]" aria-live="polite" aria-atomic="true">
      {/* Trail — previous thought fades out dimly */}
      {prevText && prevText !== displayText && (
          <p
            key={`trail-${prevText.slice(0, 20)}`}
            className="text-[10px] leading-relaxed text-slate-500/70 line-clamp-1 italic pointer-events-none select-none"
          >
            {prevText}
          </p>
        )}

        <p
          key={key}
          className="text-[12px] leading-relaxed text-foreground/70 whitespace-pre-wrap break-words font-medium font-mono tracking-tight"
        >
          <span className="mr-2 font-black" style={{ color: "#22D3EE" }}>/</span>
          {displayText}
          {/* Animated dots while actively running */}
          {active && (
            <span className="inline-block ml-0.5 font-bold" style={{ color: "rgba(34,211,238,0.6)" }}>
              {dots}
            </span>
          )}
          {/* Subtle pulsing cursor while actively running */}
          {active && (
            <span
              className="inline-block ml-1 w-[4px] h-[12px] align-middle -translate-y-px animate-pulse"
              style={{ background: "rgba(34,211,238,0.4)" }}
            />
          )}
        </p>
    </div>
  );
}

// ── Smarter live thinking text ────────────────────────────────────────────────
/**
 * Translate the raw working-memory task string into a short, user-friendly
 * action sentence so the card body reads like real forensic work is happening.
 */
function humaniseThinking(raw: string, _agentId: string): string {
  if (!raw) return "Analyzing evidence…";

  // If the backend already humanised the text (contains emoji or progress counter
  // like "(3/8)"), return it as-is to avoid double-processing.
  const hasEmoji = /[\u{1F300}-\u{1FFFF}]|[\u2600-\u27FF]/u.test(raw);
  const hasProgressCounter = /\(\d+\/\d+\)/.test(raw);
  if (hasEmoji || hasProgressCounter) return raw;

  const r = raw.toLowerCase();

  // Deep pass phrases
  if (r.includes("gemini")) return "🔬 Asking Gemini AI to examine the image…";
  if (r.includes("copy-move") || r.includes("copy move")) return "🔍 Checking for copy-move cloning artifacts…";
  if (r.includes("semantic image") || r.includes("image type")) return "🧠 Identifying what this image actually shows…";
  if (r.includes("ocr") || r.includes("visible text")) return "📄 Extracting all visible text from the image…";
  if (r.includes("adversarial")) return "🛡️ Testing against anti-forensics evasion techniques…";

  // Agent-1 
  if (r.includes("ela") && r.includes("full")) return "🔬 Running Error Level Analysis across full image…";
  if (r.includes("ela") && r.includes("block")) return "🧩 Classifying ELA anomaly blocks in flagged regions…";
  if (r.includes("ela") && r.includes("roi")) return "🔍 Re-analysing flagged ROIs with noise footprint…";
  if (r.includes("jpeg ghost")) return "👻 Running JPEG ghost detection on suspicious regions…";
  if (r.includes("frequency domain") && r.includes("gan")) return "📡 Scanning frequency domain for GAN artifacts…";
  if (r.includes("frequency domain")) return "📡 Running frequency-domain analysis on contested regions…";
  if (r.includes("file hash") || (r.includes("hash") && r.includes("verify"))) return "🔑 Verifying file hash against ingestion record…";
  if (r.includes("perceptual hash")) return "🔑 Computing perceptual hash for similarity detection…";
  if (r.includes("roi") || r.includes("region of interest")) return "🎯 Isolating and re-analysing flagged ROIs…";
  if (r.includes("noise footprint") || (r.includes("noise") && r.includes("fingerprint"))) return "📷 Analysing regional noise consistency…";
  if (r.includes("prnu") || r.includes("camera sensor")) return "📷 Running PRNU sensor fingerprint analysis…";
  if (r.includes("cfa") || r.includes("demosaicing")) return "🌈 Checking CFA Bayer pattern consistency…";

  // Agent-2 audio
  if (r.includes("speaker diarization") || r.includes("diarization")) return "🎙️ Establishing voice-count baseline with diarization…";
  if (r.includes("anti-spoofing") || r.includes("spoofing")) return "🔊 Running anti-spoofing detection on speaker segments…";
  if (r.includes("prosody")) return "🎵 Analysing prosody across the full audio track…";
  if (r.includes("splice") || r.includes("splice point")) return "✂️ Detecting ML splice points in audio segments…";
  if (r.includes("background noise") || r.includes("noise consistency")) return "🌊 Checking background noise consistency for edit points…";
  if (r.includes("codec fingerprint") || r.includes("re-encoding")) return "🔐 Fingerprinting codec chain for re-encoding events…";
  if (r.includes("audio-visual sync") || r.includes("sync")) return "⏱️ Verifying audio-visual sync against video timestamps…";

  // Agent-3 object
  if (r.includes("primary object detection") || r.includes("full-scene")) return "👁️ Running YOLO primary object detection on scene…";
  if (r.includes("secondary classification") || r.includes("confidence threshold")) return "🔎 Running secondary classification on low-confidence objects…";
  if (r.includes("scale") && r.includes("proportion")) return "📐 Validating object scale and proportion geometry…";
  if (r.includes("lighting") && r.includes("shadow")) return "💡 Checking lighting and shadow consistency per object…";
  if (r.includes("contraband") || r.includes("weapons database")) return "⚠️ Cross-referencing detected objects against contraband database…";
  if (r.includes("scene") && r.includes("contextual")) return "🧠 Analysing scene for contextual incongruences…";
  if (r.includes("image splicing") || r.includes("splice detection")) return "✂️ Running ML-based image splicing detection…";
  if (r.includes("inter-agent") || r.includes("inter_agent")) return "🤝 Issuing inter-agent call to Agent 1 for corroboration…";
  if (r.includes("document authenticity") || r.includes("font consistency")) return "📑 Checking document font consistency and forgery artifacts…";

  // Agent-4 video
  if (r.includes("optical flow") || r.includes("temporal anomaly")) return "🎬 Running optical flow analysis — building anomaly heatmap…";
  if (r.includes("frame-to-frame") || r.includes("frame consistency")) return "🖼️ Extracting frames and checking inter-frame consistency…";
  if (r.includes("explainable") || r.includes("suspicious")) return "🏷️ Classifying anomalies as EXPLAINABLE or SUSPICIOUS…";
  if (r.includes("face-swap") || r.includes("face swap")) return "🧑‍💻 Running face-swap detection on human faces…";
  if (r.includes("rolling shutter") || r.includes("compression pattern")) return "📷 Validating rolling shutter and compression vs device metadata…";

  // Agent-5 metadata
  if (r.includes("exif")) return "📋 Extracting all EXIF fields and logging absent mandatory fields…";
  if (r.includes("gps") || r.includes("timezone")) return "🌍 Cross-validating GPS coordinates against timestamp timezone…";
  if (r.includes("steganography") || r.includes("steg")) return "🕵️ Scanning for hidden steganographic payload…";
  if (r.includes("file structure") || (r.includes("hex") && r.includes("scan")) || r.includes("hexadecimal")) return "🗂️ Running hex scan for software signature anomalies…";
  if (r.includes("cross-field") || r.includes("consistency verdict")) return "📊 Synthesising cross-field metadata consistency verdict…";
  if (r.includes("c2pa") || r.includes("content credentials") || r.includes("provenance")) return "🔏 Verifying C2PA Content Credentials and provenance chain…";
  if (r.includes("thumbnail") && r.includes("mismatch")) return "🖼️ Comparing embedded thumbnail to main image — edit check…";
  if (r.includes("astronomical") || r.includes("sun position")) return "🔭 Running astronomical API check for GPS/timestamp validation…";
  if (r.includes("reverse image")) return "🌐 Running reverse image search for prior online appearances…";
  if (r.includes("device fingerprint")) return "🔐 Querying device fingerprint database for claimed device…";

  // Generic states
  if (r.includes("self-reflection") || r.includes("reflection pass")) return "🪞 Running self-reflection quality check on findings…";
  if (r.includes("submit") || r.includes("arbiter")) return "📤 Submitting calibrated findings to Council Arbiter…";
  if (r.includes("finalizing") || r.includes("finali")) return "✅ Finalising findings…";
  if (r.includes("initializing") || r.includes("initialising")) return "⚙️ Initialising analysis pipeline…";
  if (r.includes("processed") || r.includes("running validation")) return "🔄 Running cross-tool validation…";

  // Pipeline-level messages (no agent id)
  if (r.includes("all agents") && r.includes("complete")) return "✅ All agents have reported — compiling council findings…";
  if (r.includes("pipeline") && r.includes("start")) return "⚡ Forensic pipeline starting up…";
  if (r.includes("dispatching") || r.includes("dispatch")) return "📡 Dispatching agents to evidence…";
  if (r.includes("calibrating") || r.includes("calibrat")) return "⚖️ Calibrating confidence scores across agents…";
  if (r.includes("synthesising") || r.includes("synthesizing")) return "🧬 Synthesising cross-modal findings…";
  if (r.includes("resolving") && r.includes("contest")) return "⚔️ Resolving contested findings between agents…";
  if (r.includes("paused") || r.includes("awaiting decision")) return "⏸ Pipeline paused — awaiting investigator decision…";
  if (r.includes("deep analysis") || r.includes("deep scan")) return "🔬 Engaging deep analysis ML models…";
  if (r.includes("connecting") || r.includes("authenticat")) return "🔐 Authenticating with forensic pipeline…";
  if (r.includes("upload") || r.includes("ingesting")) return "📥 Ingesting evidence into secure analysis environment…";
  if (r.includes("queuing") || r.includes("queue")) return "🗂️ Queuing agents for evidence dispatch…";
  if (r.includes("warming") || r.includes("warm up")) return "🔥 Warming up ML inference engines…";

  // Fallback — capitalise raw and append ellipsis
  return raw.charAt(0).toUpperCase() + raw.slice(1);
}

// ── Main component ─────────────────────────────────────────────────────────────
export function AgentProgressDisplay({
  agentUpdates,
  completedAgents,
  progressText,
  allAgentsDone,
  phase,
  awaitingDecision,
  pipelineStatus,
  pipelineMessage,
  onAcceptAnalysis,
  onDeepAnalysis,
  onNewUpload,
  onViewResults,
  playSound,
  isNavigating = false,
}: AgentProgressDisplayProps) {
  const allValidAgents = AGENTS_DATA.filter(a => a.name !== "Council Arbiter");

  // ── Per-agent thinking staleness tracking ─────────────────────────────────
  // Track when the thinking text last changed so we can show elapsed time
  // when an agent appears stuck (e.g. during a slow Gemini API call).
  const lastThinkingTextRef = useRef<Record<string, string>>({});
  const thinkingStartRef = useRef<Record<string, number>>({});
  const [elapsedTick, setElapsedTick] = useState(0);

  useEffect(() => {
    Object.entries(agentUpdates).forEach(([id, upd]) => {
      const prev = lastThinkingTextRef.current[id];
      if (upd.thinking && upd.thinking !== prev) {
        lastThinkingTextRef.current[id] = upd.thinking;
        thinkingStartRef.current[id] = Date.now();
      }
    });
  }, [agentUpdates]);

  useEffect(() => {
    const id = setInterval(() => setElapsedTick(t => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const [unsupportedAgents, setUnsupportedAgents] = useState<Set<string>>(new Set());
  const [hiddenUnsupportedAgents, setHiddenUnsupportedAgents] = useState<Set<string>>(new Set());
  const [showSkipped, setShowSkipped] = useState(false);

  const baseVisibleAgents = phase === "deep"
    ? allValidAgents.filter(a => !unsupportedAgents.has(a.id))
    : allValidAgents;
    
  const visibleAgents = baseVisibleAgents.filter(a => !hiddenUnsupportedAgents.has(a.id));

  const hasVisibleAgents = visibleAgents.length > 0;
  const firstVisibleAgent = visibleAgents[0];
  const firstVisibleId = firstVisibleAgent ? firstVisibleAgent.id : null;

  // Stagger reveal
  const [revealedAgents, setRevealedAgents] = useState<Set<string>>(new Set());
  const prevRevealedRef = useRef<Set<string>>(new Set());

  // ── Sound: play on new card reveal ───────────────────────────────────────
  // We gate on a "user has interacted" flag so AudioContext is already unlocked.
  const hasInteractedRef = useRef(false);
  useEffect(() => {
    const unlock = () => { hasInteractedRef.current = true; };
    window.addEventListener("pointerdown", unlock, { once: true });
    window.addEventListener("keydown", unlock, { once: true });
    return () => {
      window.removeEventListener("pointerdown", unlock);
      window.removeEventListener("keydown", unlock);
    };
  }, []);

  useEffect(() => {
    if (!playSound) return;
    revealedAgents.forEach(id => {
      if (!prevRevealedRef.current.has(id)) {
        const idx = [...revealedAgents].indexOf(id);
        // First card: scan sweep sound; subsequent: soft chime
        setTimeout(() => playSound(idx === 0 ? "scan" : "agent"), idx * 90);
      }
    });
    prevRevealedRef.current = new Set(revealedAgents);
  }, [revealedAgents, playSound]);

  // Stagger reveal — reset on phase change
  useEffect(() => {
    setRevealedAgents(new Set());
    prevRevealedRef.current = new Set();
    if (!hasVisibleAgents || !firstVisibleId) return;

    setRevealedAgents(new Set([firstVisibleId]));
    let currentIndex = 1;
    const id = setInterval(() => {
      if (currentIndex >= visibleAgents.length) { clearInterval(id); return; }
      const agentId = visibleAgents[currentIndex]?.id;
      if (agentId) setRevealedAgents(prev => new Set([...prev, agentId]));
      currentIndex++;
    }, 80);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, visibleAgents.length, firstVisibleId]);

  // Detect unsupported agents — only mark as unsupported if the backend
  // explicitly set status to "skipped" or the error message clearly indicates
  // the media format is not applicable.  Do NOT rely on findings_count/ confidence
  // being zero since an agent can legitimately report zero findings on clean media.
  useEffect(() => {
    completedAgents.forEach(agent => {
      const isUnsupported =
        agent.status === "skipped" ||
        (agent.error && /not applicable|not supported|format not supported|skipping/i.test(agent.error));
      if (isUnsupported && !unsupportedAgents.has(agent.agent_id)) {
        setUnsupportedAgents(prev => new Set([...prev, agent.agent_id]));
      }
    });
  }, [completedAgents, unsupportedAgents]);

  // Auto-hide unsupported (skipped) agents after 12 seconds to declutter UI
  useEffect(() => {
    const timers: ReturnType<typeof setTimeout>[] = [];
    unsupportedAgents.forEach(id => {
      if (!hiddenUnsupportedAgents.has(id)) {
        const timer = setTimeout(() => {
          setHiddenUnsupportedAgents(prev => new Set([...prev, id]));
        }, 12000);
        timers.push(timer);
      }
    });
    return () => timers.forEach(clearTimeout);
  }, [unsupportedAgents, hiddenUnsupportedAgents]);

  const getAgentStatus = (agentId: string) => {
    if (unsupportedAgents.has(agentId)) return "unsupported";
    const completed = completedAgents.find(c => c.agent_id === agentId);
    if (completed) {
      if (completed.status === "skipped") return "unsupported";
      return completed.error ? "error" : "complete";
    }
    if (agentUpdates[agentId]) return "running";
    if (revealedAgents.has(agentId)) return "checking";
    return "waiting";
  };

  const getAgentThinking = (agentId: string) => agentUpdates[agentId]?.thinking || "";
  const getAgentFindings = (agentId: string) => completedAgents.find(c => c.agent_id === agentId);

  // Count ALL base agents that have responded (including skipped/unsupported) so the
  // header always shows the true total (e.g. "5/5" not "5/4" when a card auto-hides).
  const activeCompletedCount = completedAgents.length;
  const visibleAgentsCount = baseVisibleAgents.length;

  const showInitialDecision = awaitingDecision && phase === "initial";
  const showDeepComplete = phase === "deep" && (allAgentsDone || pipelineStatus === "complete");

  return (
    <div
      key="progress"
      className="flex flex-col items-center pt-8 relative min-h-[60vh] w-full"
    >
      {/* Background Neural Wave */}
      <div className="absolute inset-0 -z-10 pointer-events-none opacity-40">
        <AnimatedWave 
          speed={0.008} 
          amplitude={40} 
          waveColor="#22d3ee" 
          opacity={0.6}
          wireframe={true}
          quality="medium"
        />
      </div>

      <div className="flex flex-col items-center w-full max-w-6xl px-4 relative z-10">
      {/* Header */}
      <div className="text-center mb-7" aria-live="polite" aria-atomic="true">
        <Badge 
          variant="secondary" 
          withDot 
          dotColor="#22D3EE" 
          className="mb-3 font-mono font-black uppercase text-[10px] tracking-widest px-4 py-1.5 border-cyan-500/20 bg-cyan-500/5 text-cyan-300"
        >
          {activeCompletedCount} / {visibleAgentsCount} Analysed
        </Badge>

        <h2
          key={phase + String(showInitialDecision) + String(showDeepComplete)}
           
          className="text-2xl md:text-3xl font-black text-white mb-2 tracking-tighter font-heading uppercase">
          {showInitialDecision
            ? "Initial Analysis Complete"
            : showDeepComplete
              ? "Deep Analysis Complete"
              : phase === "deep"
                ? "Deep Analysis"
                : "Initial Analysis"}
        </h2>
        <div className="w-12 h-[2px] mx-auto rounded-full opacity-50" style={{ background: "#22D3EE", boxShadow: "0 0 10px rgba(34,211,238,0.4)" }} />
      </div>

      {/* Agent Cards Grid — 3-col on large screens for a clean 3×2 layout */}
      <div className="w-full max-w-6xl grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {visibleAgents.map((agent) => {
          const status = getAgentStatus(agent.id);
          const rawThinking = getAgentThinking(agent.id);
          const thinking = humaniseThinking(rawThinking, agent.id);
          const completed = getAgentFindings(agent.id);
          const isRevealed = revealedAgents.has(agent.id);

          return (
            <React.Fragment key={agent.id}>
              {isRevealed && (
                <div
                  className={clsx(
                    "rounded-2xl p-5 transition-all duration-500 relative group overflow-hidden",
                    (status === "waiting" || status === "checking") && "opacity-40",
                    status === "running" && "shadow-[0_0_30px_rgba(34,211,238,0.08)]",
                    status === "complete" && "shadow-[0_0_20px_rgba(52,211,153,0.05)]",
                    status === "error" && "shadow-[0_0_20px_rgba(248,113,113,0.05)]"
                  )}
                  style={{
                    background: status === "running"
                      ? "rgba(34,211,238,0.03)"
                      : status === "complete"
                        ? "rgba(52,211,153,0.02)"
                        : status === "error"
                          ? "rgba(248,113,113,0.02)"
                          : "rgba(255,255,255,0.02)",
                    backdropFilter: "blur(20px) saturate(150%)",
                    WebkitBackdropFilter: "blur(20px) saturate(150%)",
                    border: status === "running"
                      ? "1px solid rgba(34,211,238,0.12)"
                      : status === "complete"
                        ? "1px solid rgba(52,211,153,0.1)"
                        : status === "error"
                          ? "1px solid rgba(248,113,113,0.1)"
                          : "1px solid rgba(255,255,255,0.05)",
                    boxShadow: `inset 0 1px 0 rgba(255,255,255,${status === "running" ? "0.06" : "0.03"}), inset 0 -1px 0 rgba(255,255,255,0.01)`,
                  }}
                >
                  {/* Glass highlight glare */}
                  <div className="absolute inset-0 bg-gradient-to-br from-white/[0.04] via-transparent to-transparent pointer-events-none" />
                  {/* Ambient glow orb for running state */}
                  {status === "running" && (
                    <div className="absolute -top-20 -right-20 w-40 h-40 rounded-full pointer-events-none" style={{ background: "radial-gradient(circle, rgba(34,211,238,0.06) 0%, transparent 70%)" }} />
                  )}
                  {status === "complete" && (
                    <div className="absolute -top-16 -right-16 w-32 h-32 rounded-full pointer-events-none" style={{ background: "radial-gradient(circle, rgba(52,211,153,0.04) 0%, transparent 70%)" }} />
                  )}
                  {/* Status indicator bar (Top hairline) */}
                  <div
                    className="absolute top-0 left-0 right-0 h-[2px] transition-all duration-500 rounded-full"
                    style={{
                      background:
                        status === "running"  ? "#22D3EE" :
                        status === "complete" ? "rgba(52,211,153,0.35)" :
                        status === "error"    ? "#F87171" :
                        status === "checking" ? "rgba(34,211,238,0.2)" : "rgba(255,255,255,0.04)",
                      boxShadow: status === "running" ? "0 0 12px rgba(34,211,238,0.6)" : "none",
                    }}
                  />

                  {/* Top row */}
                  <div className="flex items-start gap-4 mb-4">
                    <div
                      className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0 transition-all duration-300"
                      style={status === "running" ? {
                        background: "rgba(34,211,238,0.07)",
                        border: "1px solid rgba(34,211,238,0.22)",
                        color: "#22D3EE",
                      } : {
                        background: "rgba(255,255,255,0.03)",
                        border: "1px solid rgba(255,255,255,0.06)",
                        color: "rgba(255,255,255,0.2)",
                      }}
                    >
                      <AgentIcon agentId={agent.id} className="w-6 h-6" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="text-base font-bold text-white leading-tight font-heading tracking-tight uppercase group-hover:text-cyan-300 transition-colors">{agent.name}</h3>
                      <span className="text-[10px] uppercase tracking-[0.2em] text-white/30 font-mono font-bold">{agent.role}</span>
                    </div>
                    <div className="shrink-0">
                      {status === "waiting" && (
                        <Badge variant="outline" className="text-foreground/40 font-bold border-white/10 bg-white/[0.03] uppercase tracking-widest font-mono">
                          Queued
                        </Badge>
                      )}
                      {status === "checking" && (
                        <Badge variant="outline" withDot dotColor="#22D3EE" className="font-black uppercase tracking-widest font-mono text-cyan-400 border-cyan-500/20 bg-cyan-500/[0.04]">
                          Linking
                        </Badge>
                      )}
                      {status === "running" && (
                        <Badge variant="outline" withDot dotColor="#22D3EE" className="font-black uppercase tracking-widest font-mono text-cyan-400 border-cyan-500/20 bg-cyan-500/[0.04]">
                          <Loader2 className="w-2.5 h-2.5 animate-spin mr-1.5" />Scan
                        </Badge>
                      )}
                      {status === "complete" && (
                        <Badge variant="outline" withDot dotColor="#10B981" className="font-bold border-emerald-500/20 bg-emerald-500/[0.04] text-emerald-400 uppercase tracking-widest font-mono">
                          Finished
                        </Badge>
                      )}
                      {status === "unsupported" && (
                        <Badge variant="outline" className="text-slate-500 font-bold border-white/10 bg-white/[0.03] uppercase tracking-widest font-mono">
                          N/A
                        </Badge>
                      )}
                      {status === "error" && (
                        <Badge variant="outline" withDot dotColor="#F87171" className="font-bold border-rose-500/20 bg-rose-500/[0.04] text-rose-400 uppercase tracking-widest font-mono">
                          Error
                        </Badge>
                      )}
                    </div>
                  </div>

                  {/* Body */}
                  {status === "checking" && (
                    <div className="space-y-2.5">
                      <p className="text-xs text-amber-300/70 leading-relaxed">
                        Agent standing by — connecting to analysis pipeline…
                      </p>
                      {/* Loading bar animation — CSS keyframe so it loops smoothly */}
                      <div className="w-full h-0.5 bg-white/[0.06] rounded-full overflow-hidden relative">
                        <div
                          className="absolute h-full w-[45%] bg-gradient-to-r from-transparent via-cyan-400/60 to-transparent rounded-full"
                          style={{ animation: "bar-slide 1.6s ease-in-out infinite" }}
                        />
                      </div>
                      {/* Skeleton tool lines */}
                      <div className="space-y-1.5 opacity-25">
                        {[75, 58, 68].map((w, i) => (
                          <div
                            key={i}
                            className="h-1.5 bg-slate-600 rounded-full"
                            style={{ width: `${w}%` }}
                            
                            
                          />
                        ))}
                      </div>
                    </div>
                  )}

                  {status === "running" && (
                    <div className="space-y-2">
                      <LiveThinkingText text={thinking} active={true} />
                      {/* Tool progress bar + staleness indicator */}
                      {(() => {
                        const upd = agentUpdates[agent.id];
                        const toolsTotal = upd?.tools_total ?? 0;
                        const toolsDone = upd?.tools_done ?? 0;
                        const pct = toolsTotal > 0
                          ? Math.min(100, Math.round((toolsDone / toolsTotal) * 100))
                          : null;

                        // Elapsed time since thinking text last changed
                        const startTs = thinkingStartRef.current[agent.id];
                        // elapsedTick is read to ensure re-render every second
                        void elapsedTick;
                        const elapsed = startTs ? Math.floor((Date.now() - startTs) / 1000) : 0;
                        const isStale = elapsed >= 8;
                        const isGeminiStep = thinking.toLowerCase().includes("gemini");
                        const isApiStep = isGeminiStep || thinking.toLowerCase().includes("api") || thinking.toLowerCase().includes("vision");

                        return (
                          <div className="space-y-1.5 mt-2">
                            {/* Progress bar — indeterminate when stale (API call in-flight) */}
                            <div className="relative w-full h-1 bg-white/5 rounded-full overflow-hidden">
                              {!isStale && pct !== null ? (
                                <div
                                  className="h-full rounded-full"
                                  style={{ background: "#22D3EE", boxShadow: "0 0 8px rgba(34,211,238,0.6)" }}
                                  
                                  
                                  
                                />
                              ) : (
                                <div
                                  className={`absolute h-full w-[45%] rounded-full ${
                                    isStale
                                      ? "bg-gradient-to-r from-transparent via-rose-500/60 to-transparent"
                                      : "bg-gradient-to-r from-transparent via-cyan-500/50 to-transparent"
                                  }`}
                                  style={{ animation: `bar-slide ${isStale ? "1.4s" : "2s"} ease-in-out infinite` }}
                                />
                              )}
                            </div>

                            {/* Tool counter row */}
                            <div className="flex justify-between items-center text-[9px] text-white/20 font-bold uppercase tracking-widest">
                              {pct !== null ? (
                                <>
                                  <span>Verification Units: {toolsDone}/{toolsTotal}</span>
                                  <span className="font-mono" style={{ color: "rgba(34,211,238,0.65)" }}>{pct}% Complete</span>
                                </>
                              ) : (
                                <span className="text-white/10 italic">Initializing tools…</span>
                              )}
                            </div>

                            {/* Staleness banner — shown after 8 s on same step */}
                            {isStale && (
                              <div
                                
                                
                                className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[10px] font-mono font-bold ${
                                  isGeminiStep
                                    ? "bg-violet-500/10 border border-violet-500/20 text-violet-300/70"
                                    : isApiStep
                                      ? "bg-blue-500/10 border border-blue-500/20 text-blue-300/70"
                                      : "bg-cyan-500/10 border border-cyan-500/20 text-cyan-300/70"
                                }`}
                              >
                                <span className="animate-pulse">●</span>
                                {isGeminiStep
                                  ? `Gemini vision analysis in progress — ${elapsed}s elapsed (30–60s typical)`
                                  : isApiStep
                                    ? `Awaiting external API response — ${elapsed}s elapsed`
                                    : `Processing — ${elapsed}s elapsed`
                                }
                              </div>
                            )}
                          </div>
                        );
                      })()}
                    </div>
                  )}

                  {status === "complete" && completed && (
                    <div className="space-y-4">
                      {/* Verdict row */}
                      {completed.agent_verdict && (
                        <div className={[
                          "flex items-center gap-4 px-5 py-4 rounded-xl overflow-hidden relative",
                          completed.agent_verdict === "AUTHENTIC"
                            ? ""
                            : completed.agent_verdict === "LIKELY_MANIPULATED"
                              ? ""
                              : "",
                        ].join(" ")}
                        style={{
                          background: completed.agent_verdict === "AUTHENTIC"
                            ? "rgba(52,211,153,0.04)"
                            : completed.agent_verdict === "LIKELY_MANIPULATED"
                              ? "rgba(244,63,94,0.04)"
                              : "rgba(34,211,238,0.04)",
                          backdropFilter: "blur(12px)",
                          WebkitBackdropFilter: "blur(12px)",
                          border: completed.agent_verdict === "AUTHENTIC"
                            ? "1px solid rgba(52,211,153,0.12)"
                            : completed.agent_verdict === "LIKELY_MANIPULATED"
                              ? "1px solid rgba(244,63,94,0.12)"
                              : "1px solid rgba(34,211,238,0.12)",
                          boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
                        }}>
                          <div className={[
                             "w-8 h-8 rounded-lg flex items-center justify-center shrink-0 border",
                             completed.agent_verdict === "AUTHENTIC" ? "bg-emerald-500/20 border-emerald-500/40 text-emerald-400" :
                             completed.agent_verdict === "LIKELY_MANIPULATED" ? "bg-red-500/20 border-red-500/40 text-red-400" :
                             "bg-cyan-500/20 border-cyan-500/40 text-cyan-400"
                          ].join(" ")}>
                            {completed.agent_verdict === "AUTHENTIC" ? "✓" : completed.agent_verdict === "LIKELY_MANIPULATED" ? "!" : "?"}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-[10px] font-bold uppercase tracking-[0.2em] leading-none mb-2 opacity-60 text-white/40">Verdict</p>
                            <Badge 
                                variant={
                                    completed.agent_verdict === "AUTHENTIC" ? "success" : 
                                    completed.agent_verdict === "LIKELY_MANIPULATED" ? "destructive" : "warning"
                                } 
                                size="lg"
                                withDot
                                className="font-black uppercase tracking-widest font-heading px-4 py-1"
                            >
                                {completed.agent_verdict.replace(/_/g, " ")}
                            </Badge>
                          </div>
                          {/* Confidence inline */}
                          {completed.confidence !== undefined && (
                            <div className="text-right shrink-0">
                               <p className="text-[9px] font-mono text-slate-500 uppercase tracking-tighter font-bold">Confidence</p>
                               <span className={[
                                "text-sm font-black tabular-nums font-mono drop-shadow-[0_0_8px_rgba(0,0,0,0.5)]",
                                completed.confidence >= 0.75 ? "text-emerald-400" :
                                completed.confidence >= 0.5  ? "text-amber-400"   : "text-red-400",
                               ].join(" ")}>
                                 {Math.round(completed.confidence * 100)}%
                               </span>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Tools summary line */}
                      {(completed.tools_ran !== undefined || completed.tools_skipped !== undefined) && (
                        <div className="flex items-center gap-3 text-[9px] font-mono uppercase tracking-widest text-slate-500">
                          {completed.tools_ran !== undefined && (
                            <span className="text-emerald-400/70">{completed.tools_ran} ran</span>
                          )}
                          {completed.tools_skipped !== undefined && completed.tools_skipped > 0 && (
                            <span className="text-slate-600">{completed.tools_skipped} n/a</span>
                          )}
                          {completed.tools_failed !== undefined && completed.tools_failed > 0 && (
                            <span className="text-amber-400/70">{completed.tools_failed} failed</span>
                          )}
                        </div>
                      )}

                      {/* Per-finding list */}
                      <div className="pt-2">
                        {completed.findings_preview && completed.findings_preview.length > 0 ? (
                          <FindingsPreviewList findings={completed.findings_preview} />
                        ) : completed.section_flags && completed.section_flags.length > 0 ? (
                          <FindingsAccordion
                            sectionFlags={completed.section_flags}
                            findingsCount={completed.findings_count}
                          />
                        ) : (
                          <div className="flex flex-col items-center justify-center p-6 rounded-2xl gap-2 relative overflow-hidden"
                            style={{
                              background: "rgba(255,255,255,0.02)",
                              backdropFilter: "blur(16px)",
                              WebkitBackdropFilter: "blur(16px)",
                              border: "1px solid rgba(255,255,255,0.05)",
                              boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
                            }}
                          >
                            <div className="absolute inset-0 bg-gradient-to-br from-white/[0.02] to-transparent pointer-events-none" />
                             <div className="w-10 h-10 rounded-full bg-emerald-500/10 flex items-center justify-center mb-1 border border-emerald-500/20">
                                <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                             </div>
                             <span className="text-[11px] text-slate-400 font-mono uppercase tracking-wider text-center leading-relaxed font-bold">
                               {completed.message || "Clearance: No Anomalies Detected"}
                             </span>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {status === "unsupported" && completed && (
                    <div className="space-y-2">
                      <p className="text-xs text-slate-300/70 leading-relaxed">
                        {completed.message || completed.error || "File type not supported."}
                      </p>
                      <p className="text-[10px] text-slate-400/50 italic">Not applicable for this evidence type.</p>
                    </div>
                  )}

                  {status === "error" && completed && (
                    <div className="space-y-1">
                      <ExpandableText
                        text={completed.error || "An error occurred."}
                        textClassName="text-rose-400"
                      />
                    </div>
                  )}

                  {status === "waiting" && (
                    <p className="text-xs text-foreground/20 font-mono italic">Awaiting dispatch...</p>
                  )}
                </div>
              )}
            </React.Fragment>
          );
        })}
      </div>

      {/* ── Skipped Agents Collapse ─────────────────────────────────── */}
      {hiddenUnsupportedAgents.size > 0 && (
        <div className="w-full max-w-5xl mt-6 flex flex-col items-center">
          <button
            onClick={() => setShowSkipped(s => !s)}
            className="flex items-center gap-2 px-4 py-2 rounded border border-white/5 bg-white/[0.02] hover:bg-white/[0.04] transition-colors text-[10px] font-black font-mono text-white/40 uppercase tracking-[0.2em] group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/50"
          >
            <span>{hiddenUnsupportedAgents.size} Skipped Units (Not Applicable)</span>
            <ChevronDown className={`w-3 h-3 transition-transform duration-200 ${showSkipped ? "rotate-180" : ""}`} />
          </button>
            {showSkipped && (
              <div
                
                
                
                
                className="overflow-hidden w-full max-w-md mt-3"
              >
                <div className="flex flex-col gap-2 p-3 rounded-xl border border-white/[0.04] bg-white/[0.01]">
                  {Array.from(hiddenUnsupportedAgents).map(agentId => {
                    const meta = AGENTS_DATA.find(a => a.id === agentId);
                    if (!meta) return null;
                    return (
                      <div key={agentId} className="flex items-center justify-between px-3 py-2 rounded-lg bg-white/[0.02] border border-white/[0.02]">
                        <div className="flex items-center gap-2">
                          <span className="w-1.5 h-1.5 rounded-full shrink-0 bg-cyan-400/50" />
                          <span className="text-sm text-slate-300 font-medium">{meta.name}</span>
                        </div>
                        <span className="text-[10px] font-black font-mono text-white/20 uppercase tracking-[0.2em]">Incompatible</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
        </div>
      )}

      {/* ── Decision Buttons ─────────────────────────────────────────── */}

      {showInitialDecision && (
        <div className="mt-8 w-full max-w-xl">
          {/* Decision card */}
          <div className="surface-panel rounded-2xl p-5 space-y-4 shadow-lg border-border-bold">
            <div className="text-center space-y-1">
              <p className="text-[10px] font-black font-mono uppercase tracking-[0.3em]" style={{ color: "#22D3EE" }}>Investigator Protocol</p>
              <h3 className="text-lg font-black text-white font-heading uppercase tracking-tighter">Initial Scan Concluded</h3>
            </div>
            <div className="flex flex-col sm:flex-row gap-3">
               <button
                onClick={onAcceptAnalysis}
                disabled={isNavigating}
                className="group flex-1 py-3.5 rounded-full text-xs font-semibold cursor-pointer flex items-center justify-center gap-2 text-white/70 hover:text-white transition-all duration-300"
                style={{ background: "transparent", border: "1px solid rgba(34,211,238,0.2)", boxShadow: "none" }}
                onMouseEnter={(e) => { e.currentTarget.style.background = "linear-gradient(135deg, rgba(6,182,212,0.15) 0%, rgba(34,211,238,0.15) 100%)"; e.currentTarget.style.borderColor = "rgba(34,211,238,0.4)"; e.currentTarget.style.boxShadow = "0 0 20px rgba(34,211,238,0.1)"; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.borderColor = "rgba(34,211,238,0.2)"; e.currentTarget.style.boxShadow = "none"; }}
              >
                {isNavigating ? (
                  <><Loader2 className="w-4 h-4 animate-spin" />Compiling...</>
                ) : (
                  <><FileText className="w-4 h-4 text-cyan-400/50" />Accept Analysis</>
                )}
              </button>
               <button
                onClick={onDeepAnalysis}
                disabled={isNavigating}
                className="group flex-1 py-3.5 rounded-full text-xs font-semibold cursor-pointer flex items-center justify-center gap-2 text-amber-400/70 hover:text-amber-300 transition-all duration-300"
                style={{ background: "transparent", border: "1px solid rgba(245,158,11,0.2)", boxShadow: "none" }}
                onMouseEnter={(e) => { e.currentTarget.style.background = "linear-gradient(135deg, rgba(217,119,6,0.15) 0%, rgba(245,158,11,0.15) 100%)"; e.currentTarget.style.borderColor = "rgba(245,158,11,0.4)"; e.currentTarget.style.boxShadow = "0 0 20px rgba(245,158,11,0.1)"; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.borderColor = "rgba(245,158,11,0.2)"; e.currentTarget.style.boxShadow = "none"; }}
              >
                <Microscope className="w-4 h-4 text-amber-400/50" />Deep Analysis
              </button>
            </div>
          </div>
        </div>
      )}

      {showDeepComplete && (
        <div
           
          
          className="mt-8 w-full max-w-xl"
        >
          <div className="surface-panel rounded-2xl p-5 space-y-4 shadow-lg border-border-bold">
            <div className="text-center space-y-1">
              <p className="text-[9px] font-mono text-emerald-500 uppercase tracking-widest font-bold">Verification Complete</p>
              <h3 className="text-base font-bold text-foreground font-heading uppercase">Council Arbiter Verification</h3>
            </div>
            <div className="flex flex-col sm:flex-row gap-3">
              <button
                onClick={() => { playSound?.("click"); onNewUpload?.(); }}
                disabled={isNavigating}
                
                
                className="btn-premium-glass flex-1 py-3 justify-center text-[11px] font-black uppercase tracking-[0.2em]"
              >
                <RotateCcw className="w-4 h-4 opacity-40" />RESET TERMINAL
              </button>
              <button
                onClick={() => { playSound?.("click"); onViewResults?.(); }}
                disabled={isNavigating}
                
                
                className="btn-premium-amber flex-1 py-3 justify-center text-[11px] font-black uppercase tracking-[0.2em] relative overflow-hidden shadow-[0_0_30px_rgba(217,119,6,0.3)]"
              >
                {isNavigating ? (
                  <><Loader2 className="w-4 h-4 animate-spin" />FINALIZING...</>
                ) : (
                  <><FileText className="w-4 h-4" />ACCESS LEDGER<ArrowRight className="w-4 h-4 ml-1" /></>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Still running */}
      {!showInitialDecision && !showDeepComplete && (
        <div className="mt-8 text-center">
          {/* Status line with animated dot */}
          <div className="inline-flex items-center gap-2">
            {!allAgentsDone && (
              <span className="relative flex h-1.5 w-1.5 shrink-0">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-40" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-cyan-400" />
              </span>
            )}
            <p className="text-sm font-medium text-foreground/50">{progressText}</p>
          </div>
          {!!pipelineMessage && (
            <div className="mt-3 max-w-xl mx-auto px-4 py-3 rounded-xl glass-panel border border-border-subtle">
              <LiveThinkingText text={humaniseThinking(pipelineMessage, "")} active={!allAgentsDone} />
            </div>
          )}
        </div>
      )}
    </div>
  </div>
);
}
