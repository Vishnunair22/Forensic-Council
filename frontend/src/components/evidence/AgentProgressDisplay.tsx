"use client";

/**
 * AgentProgressDisplay Component
 * ================================
 * Shows agent cards in a grid with real-time status, expandable findings,
 * and decision buttons after each analysis phase.
 */

import React from "react";
import { clsx } from "clsx";
import {
  CheckCircle2,
  Loader2,
  ArrowRight,
  AlertTriangle,
  RotateCcw,
  Microscope,
  FileText,
  ChevronDown,
  Wrench,
  Clock,
} from "lucide-react";
import { AgentIcon } from "@/components/ui/AgentIcon";
import { Badge } from "@/components/lightswind/badge";
import AnimatedWave from "@/components/lightswind/animated-wave";
import { AGENTS_DATA } from "@/lib/constants";
import { useState, useEffect, useRef, useMemo } from "react";
import { SoundType } from "@/hooks/useSound";
import { fmtTool } from "@/lib/fmtTool";

// ── Interfaces ─────────────────────────────────────────────────────────────────

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
  elapsed_s?: number | null;
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
  agent_verdict?: "AUTHENTIC" | "LIKELY_MANIPULATED" | "INCONCLUSIVE" | null;
  tool_error_rate?: number;
  section_flags?: SectionFlag[];
  findings_preview?: FindingPreview[];
  tools_ran?: number;
  tools_skipped?: number;
  tools_failed?: number;
  completed_at?: string;
}

interface AgentProgressDisplayProps {
  agentUpdates: Record<
    string,
    {
      status: string;
      thinking: string;
      tools_done?: number;
      tools_total?: number;
    }
  >;
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

// ── Expandable text helper ─────────────────────────────────────────────────────

const CLAMP_CHARS = 200;

function ExpandableText({
  text,
  className,
}: {
  text: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const needsClamp = text.length > CLAMP_CHARS;
  const display =
    needsClamp && !open ? text.slice(0, CLAMP_CHARS).trimEnd() + "…" : text;

  return (
    <div>
      <p
        className={clsx(
          "text-[12px] leading-relaxed whitespace-pre-wrap break-words",
          className || "text-slate-300",
        )}
      >
        {display}
      </p>
      {needsClamp && (
        <button
          onClick={() => setOpen((v) => !v)}
          className="mt-1 text-[10px] font-bold uppercase tracking-[0.15em] text-cyan-400/70 hover:text-cyan-300 transition-colors"
        >
          {open ? "▲ Show less" : "▼ Show more"}
        </button>
      )}
    </div>
  );
}

// ── Verdict colours ────────────────────────────────────────────────────────────

const VERDICT_STYLES: Record<
  string,
  {
    bg: string;
    border: string;
    text: string;
    badge: "success" | "destructive" | "warning" | "outline";
  }
> = {
  AUTHENTIC: {
    bg: "rgba(52,211,153,0.04)",
    border: "rgba(52,211,153,0.12)",
    text: "text-emerald-400",
    badge: "success",
  },
  LIKELY_MANIPULATED: {
    bg: "rgba(244,63,94,0.04)",
    border: "rgba(244,63,94,0.12)",
    text: "text-red-400",
    badge: "destructive",
  },
  INCONCLUSIVE: {
    bg: "rgba(251,191,36,0.04)",
    border: "rgba(251,191,36,0.12)",
    text: "text-amber-400",
    badge: "warning",
  },
};

const TOOL_VERDICT_STYLES: Record<
  string,
  { border: string; text: string; bg: string }
> = {
  CLEAN: {
    border: "border-emerald-500/30",
    text: "text-emerald-400",
    bg: "bg-emerald-500/10",
  },
  FLAGGED: {
    border: "border-red-500/30",
    text: "text-red-400",
    bg: "bg-red-500/10",
  },
  NOT_APPLICABLE: {
    border: "border-slate-500/30",
    text: "text-slate-500",
    bg: "bg-slate-500/10",
  },
  ERROR: {
    border: "border-amber-500/30",
    text: "text-amber-400",
    bg: "bg-amber-500/10",
  },
};

// ── Confidence colour helper ───────────────────────────────────────────────────

function confidenceColor(val: number): string {
  if (val >= 0.75) return "text-emerald-400";
  if (val >= 0.5) return "text-amber-400";
  return "text-red-400";
}

function confidenceBg(val: number): string {
  if (val >= 0.75) return "bg-emerald-500/10";
  if (val >= 0.5) return "bg-amber-500/10";
  return "bg-red-500/10";
}

// ── Tool icon helper ───────────────────────────────────────────────────────────

function ToolIcon({ className }: { className?: string }) {
  return (
    <Wrench className={clsx("w-3.5 h-3.5", className)} aria-hidden="true" />
  );
}

// ── Tool Card ──────────────────────────────────────────────────────────────────
// Renders a single tool: icon + name + elapsed time on one row,
// then the finding summary below with expand.

function ToolCard({
  finding,
}: {
  finding: FindingPreview;
}) {
  const tv = TOOL_VERDICT_STYLES[finding.verdict] ?? TOOL_VERDICT_STYLES.CLEAN;
  const elapsedLabel =
    finding.elapsed_s != null
      ? finding.elapsed_s < 1
        ? "<1s"
        : `${Math.round(finding.elapsed_s)}s`
      : null;

  return (
    <div
      className={clsx(
        "rounded-xl border overflow-hidden transition-colors",
        tv.border,
      )}
      style={{ background: "rgba(255,255,255,0.015)" }}
    >
      {/* Tool header row */}
      <div className="flex items-center gap-2.5 px-4 py-2.5 border-b border-white/[0.04]">
        <span className={clsx("flex-shrink-0", tv.text)}>
          <ToolIcon />
        </span>
        <span
          className="text-[11px] font-black tracking-[0.1em] uppercase flex-1 font-mono"
          style={{ color: "rgba(34,211,238,0.85)" }}
        >
          {fmtTool(finding.tool)}
        </span>
        <div className="flex items-center gap-2 flex-shrink-0">
          {/* Verdict pill */}
          <span
            className={clsx(
              "text-[8px] font-mono font-black px-1.5 py-0.5 rounded border uppercase tracking-wider",
              tv.text,
              tv.bg,
              tv.border,
            )}
          >
            {finding.verdict === "NOT_APPLICABLE" ? "N/A" : finding.verdict}
          </span>
          {/* Confidence */}
          {finding.verdict !== "NOT_APPLICABLE" && (
            <span
              className={clsx(
                "text-[10px] font-mono font-bold px-1.5 py-0.5 rounded",
                confidenceColor(finding.confidence),
                confidenceBg(finding.confidence),
              )}
            >
              {Math.round(finding.confidence * 100)}%
            </span>
          )}
          {/* Elapsed time */}
          {elapsedLabel && (
            <span className="flex items-center gap-1 text-[9px] font-mono text-slate-500">
              <Clock className="w-2.5 h-2.5" />
              {elapsedLabel}
            </span>
          )}
        </div>
      </div>

      {/* Finding summary */}
      <div className="px-4 py-3">
        <ExpandableText text={finding.summary} />
        {finding.key_signal && finding.key_signal !== finding.summary && (
          <p className="mt-2 text-[10px] text-cyan-400/50 font-mono leading-relaxed pl-2 border-l border-cyan-500/20">
            {finding.key_signal}
          </p>
        )}
      </div>
    </div>
  );
}

// ── Live Thinking Text ─────────────────────────────────────────────────────────

function humaniseThinking(raw: string, _agentId: string): string {
  if (!raw) return "Analyzing evidence…";

  const stripRegex = /[\u{1F300}-\u{1FFFF}]|[\u2600-\u27FF]/gu;
  const noEmojiRaw = raw.replace(stripRegex, "").trim();

  const hasProgressCounter = /\(\d+\/\d+\)/.test(noEmojiRaw);
  if (hasProgressCounter) return noEmojiRaw;

  const r = noEmojiRaw.toLowerCase();

  if (r.includes("gemini")) return "Asking Gemini AI to examine the image…";
  if (r.includes("ela") && r.includes("full"))
    return "Running Error Level Analysis across full image…";
  if (r.includes("ela") && r.includes("block"))
    return "Classifying ELA anomaly blocks in flagged regions…";
  if (r.includes("jpeg ghost"))
    return "Running JPEG ghost detection on suspicious regions…";
  if (r.includes("frequency domain"))
    return "Running frequency-domain analysis…";
  if (r.includes("file hash") || (r.includes("hash") && r.includes("verify")))
    return "Verifying file hash against ingestion record…";
  if (r.includes("prnu") || r.includes("camera sensor"))
    return "Running PRNU sensor fingerprint analysis…";
  if (r.includes("cfa") || r.includes("demosaicing"))
    return "Checking CFA Bayer pattern consistency…";
  if (r.includes("copy-move") || r.includes("copy move"))
    return "Checking for copy-move cloning artifacts…";
  if (r.includes("ocr") || r.includes("visible text"))
    return "Extracting all visible text from the image…";
  if (r.includes("exif")) return "Extracting all EXIF fields…";
  if (r.includes("steganography") || r.includes("steg"))
    return "Scanning for hidden steganographic payload…";
  if (r.includes("gps") || r.includes("timezone"))
    return "Cross-validating GPS coordinates against timestamp timezone…";
  if (r.includes("optical flow"))
    return "Running optical flow analysis — building anomaly heatmap…";
  if (r.includes("face-swap") || r.includes("face swap"))
    return "Running face-swap detection on human faces…";
  if (r.includes("object detection") || r.includes("yolo"))
    return "Running YOLO primary object detection…";
  if (r.includes("self-reflection"))
    return "Running self-reflection quality check…";
  if (r.includes("submit") || r.includes("arbiter"))
    return "Submitting calibrated findings to Council Arbiter…";
  if (r.includes("finalizing") || r.includes("finali"))
    return "Finalising findings…";

  const finalStr = noEmojiRaw.charAt(0).toUpperCase() + noEmojiRaw.slice(1);
  return finalStr.replace(stripRegex, "").trim();
}

function LiveThinkingText({ text, active }: { text: string; active: boolean }) {
  const [displayText, setDisplayText] = useState(text);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [dotCount, setDotCount] = useState(1);

  useEffect(() => {
    if (text === displayText) return;
    timerRef.current = setTimeout(() => setDisplayText(text), 150);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [text, displayText]);

  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setDotCount((c) => (c % 3) + 1), 600);
    return () => clearInterval(id);
  }, [active]);

  const dots = active ? ".".repeat(dotCount) : "";

  return (
    <div aria-live="polite" aria-atomic="true">
      <p className="text-[11px] leading-relaxed text-foreground/60 font-mono tracking-tight">
        <span className="mr-1.5 font-black" style={{ color: "#22D3EE" }}>
          /
        </span>
        {displayText}
        {active && (
          <span
            className="ml-0.5 font-bold"
            style={{ color: "rgba(34,211,238,0.6)" }}
          >
            {dots}
          </span>
        )}
      </p>
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────

const allValidAgents = AGENTS_DATA.filter(
  (a) => a.name !== "Council Arbiter",
);

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
  // ── Stagger reveal ─────────────────────────────────────────────────────────
  const [revealedAgents, setRevealedAgents] = useState<Set<string>>(new Set());
  const [unsupportedAgents, setUnsupportedAgents] = useState<Set<string>>(
    new Set(),
  );
  const [hiddenUnsupportedAgents, setHiddenUnsupportedAgents] = useState<
    Set<string>
  >(new Set());
  const [fadingOutAgents, setFadingOutAgents] = useState<Set<string>>(
    new Set(),
  );

  const baseVisibleAgents = useMemo(
    () =>
      phase === "deep"
        ? allValidAgents.filter((a) => !unsupportedAgents.has(a.id))
        : allValidAgents,
    [phase, unsupportedAgents],
  );
  const visibleAgents = useMemo(
    () =>
      baseVisibleAgents.filter((a) => !hiddenUnsupportedAgents.has(a.id)),
    [baseVisibleAgents, hiddenUnsupportedAgents],
  );

  const firstVisibleId = visibleAgents[0]?.id ?? null;

  useEffect(() => {
    setRevealedAgents(new Set());
    if (!visibleAgents.length || !firstVisibleId) return;
    setRevealedAgents(new Set([firstVisibleId]));
    let idx = 1;
    const id = setInterval(() => {
      if (idx >= visibleAgents.length) {
        clearInterval(id);
        return;
      }
      const aid = visibleAgents[idx]?.id;
      if (aid) setRevealedAgents((prev) => new Set([...prev, aid]));
      idx++;
    }, 80);
    return () => clearInterval(id);
  }, [phase, visibleAgents, firstVisibleId]);

  // ── Sound on reveal ────────────────────────────────────────────────────────
  const hasInteractedRef = useRef(false);
  useEffect(() => {
    const unlock = () => {
      hasInteractedRef.current = true;
    };
    window.addEventListener("pointerdown", unlock, { once: true });
    window.addEventListener("keydown", unlock, { once: true });
    return () => {
      window.removeEventListener("pointerdown", unlock);
      window.removeEventListener("keydown", unlock);
    };
  }, []);

  const prevRevealedRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    if (!playSound) return;
    revealedAgents.forEach((id) => {
      if (!prevRevealedRef.current.has(id)) {
        const idx = [...revealedAgents].indexOf(id);
        setTimeout(() => playSound(idx === 0 ? "scan" : "agent"), idx * 90);
      }
    });
    prevRevealedRef.current = new Set(revealedAgents);
  }, [revealedAgents, playSound]);

  // ── Unsupported detection ──────────────────────────────────────────────────
  useEffect(() => {
    setUnsupportedAgents((prev) => {
      const next = new Set(prev);
      completedAgents.forEach((agent) => {
        const isUnsupported =
          agent.status === "skipped" ||
          (agent.error &&
            /not applicable|not supported|format not supported|skipping/i.test(
              agent.error,
            ));
        if (isUnsupported) {
          next.add(agent.agent_id);
        }
      });
      return next;
    });
  }, [completedAgents]);

  // Store timers in a ref so React effect cleanup never cancels them prematurely.
  // Each skipped agent gets exactly one 10s timer, started when it is revealed.
  const hideTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const fadeOutTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  useEffect(() => {
    revealedAgents.forEach((id) => {
      if (unsupportedAgents.has(id) && !hideTimersRef.current.has(id)) {
        const timer = setTimeout(() => {
          setFadingOutAgents((prev) => new Set([...prev, id]));
          const fadeOutTimer = setTimeout(() => {
            setHiddenUnsupportedAgents((prev) => new Set([...prev, id]));
            setFadingOutAgents((prev) => {
              const next = new Set(prev);
              next.delete(id);
              return next;
            });
            hideTimersRef.current.delete(id);
            fadeOutTimersRef.current.delete(id);
          }, 500);
          fadeOutTimersRef.current.set(id, fadeOutTimer);
        }, 10000);
        hideTimersRef.current.set(id, timer);
      }
    });
  }, [revealedAgents, unsupportedAgents]);
  // Clear any pending timers on unmount only
  useEffect(() => {
    return () => {
      hideTimersRef.current.forEach((t) => clearTimeout(t));
      hideTimersRef.current.clear();
      fadeOutTimersRef.current.forEach((t) => clearTimeout(t));
      fadeOutTimersRef.current.clear();
    };
  }, []);

  // ── Status helpers ─────────────────────────────────────────────────────────
  const getAgentStatus = (agentId: string) => {
    if (unsupportedAgents.has(agentId)) return "unsupported";
    const completed = completedAgents.find((c) => c.agent_id === agentId);
    if (completed) {
      if (completed.status === "skipped") return "unsupported";
      return completed.error ? "error" : "complete";
    }
    if (agentUpdates[agentId]) return "running";
    if (revealedAgents.has(agentId)) return "checking";
    return "waiting";
  };

  const getAgentThinking = (agentId: string) =>
    agentUpdates[agentId]?.thinking || "";
  const getAgentFindings = (agentId: string) =>
    completedAgents.find((c) => c.agent_id === agentId);

  const activeCompletedCount = completedAgents.length;
  const visibleAgentsCount = baseVisibleAgents.length;

  const showInitialDecision = awaitingDecision && phase === "initial";
  const showDeepComplete =
    phase === "deep" && (allAgentsDone || pipelineStatus === "complete");

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
          wireframe
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
          <h2 className="text-2xl md:text-3xl font-black text-white mb-2 tracking-tighter font-heading uppercase">
            {showInitialDecision
              ? "Initial Analysis Complete"
              : showDeepComplete
                ? "Deep Analysis Complete"
                : phase === "deep"
                  ? "Deep Analysis"
                  : "Initial Analysis"}
          </h2>
          <div
            className="w-12 h-[2px] mx-auto rounded-full opacity-50"
            style={{
              background: "#22D3EE",
              boxShadow: "0 0 10px rgba(34,211,238,0.4)",
            }}
          />
        </div>

        {/* Agent Cards */}
        <div 
          className="w-full max-w-6xl grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5"
          role="list"
          aria-label="Agent analysis results"
        >
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
                      "rounded-2xl p-5 transition-all duration-500 relative overflow-hidden flex flex-col h-full glass-panel",
                      fadingOutAgents.has(agent.id) && "opacity-0 scale-95",
                      (status === "waiting" || status === "checking") &&
                        "opacity-40",
                      status === "running" &&
                        "shadow-[0_0_30px_rgba(34,211,238,0.08)]",
                      status === "complete" &&
                        "shadow-[0_0_20px_rgba(52,211,153,0.05)]",
                      status === "error" &&
                        "shadow-[0_0_20px_rgba(248,113,113,0.05)]",
                    )}
                    style={{
                      border:
                        status === "running"
                          ? "1px solid rgba(34,211,238,0.12)"
                          : status === "complete"
                            ? "1px solid rgba(52,211,153,0.1)"
                            : status === "error"
                              ? "1px solid rgba(248,113,113,0.1)"
                              : undefined,
                    }}
                    role="listitem"
                    tabIndex={0}
                    aria-label={`${agent.name}: ${status}`}
                    aria-describedby={`agent-${agent.id}-status`}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        // Expand/collapse card details
                      }
                    }}
                  >
                    {/* Glass highlight */}
                    <div className="absolute inset-0 bg-gradient-to-br from-white/[0.04] via-transparent to-transparent pointer-events-none" />
                    {/* Top hairline */}
                    <div
                      className="absolute top-0 left-0 right-0 h-[2px] transition-all duration-500 rounded-full"
                      style={{
                        background:
                          status === "running"
                            ? "#22D3EE"
                            : status === "complete"
                              ? "rgba(52,211,153,0.35)"
                              : status === "error"
                                ? "#F87171"
                                : "rgba(255,255,255,0.04)",
                        boxShadow:
                          status === "running"
                            ? "0 0 12px rgba(34,211,238,0.6)"
                            : "none",
                      }}
                    />

                    {/* ═══ HEADER: Agent icon + name + status badge ═══ */}
                    <div className="flex items-center gap-3 mb-4">
                      <div
                        className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0 transition-all duration-300"
                        style={
                          status === "running"
                            ? {
                                background: "rgba(34,211,238,0.07)",
                                border: "1px solid rgba(34,211,238,0.22)",
                                color: "#22D3EE",
                              }
                            : {
                                background: "rgba(255,255,255,0.03)",
                                border: "1px solid rgba(255,255,255,0.06)",
                                color: "rgba(255,255,255,0.2)",
                              }
                        }
                      >
                        <AgentIcon agentId={agent.id} className="w-6 h-6" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <h3 className="text-sm font-bold text-white leading-tight font-heading tracking-tight uppercase">
                          {agent.name}
                        </h3>
                        <span className="text-[10px] uppercase tracking-[0.15em] text-white/40 font-mono font-bold">
                          {agent.badge}
                        </span>
                      </div>
                        {/* Status badge */}
                        <div 
                          className="shrink-0"
                          id={`agent-${agent.id}-status`}
                          role="status"
                          aria-live="polite"
                        >
                          {status === "waiting" && (
                            <Badge
                              variant="outline"
                              className="text-foreground/40 font-bold border-white/10 bg-white/[0.03] uppercase tracking-widest font-mono text-[9px]"
                            >
                              Queued
                            </Badge>
                          )}
                          {status === "checking" && (
                            <Badge
                              variant="outline"
                              withDot
                              dotColor="#22D3EE"
                              className="font-black uppercase tracking-widest font-mono text-cyan-400 border-cyan-500/20 bg-cyan-500/[0.04] text-[9px]"
                            >
                              Linking
                            </Badge>
                          )}
                          {status === "running" && (
                            <Badge
                              variant="outline"
                              withDot
                            dotColor="#22D3EE"
                            className="font-black uppercase tracking-widest font-mono text-cyan-400 border-cyan-500/20 bg-cyan-500/[0.04] text-[9px]"
                          >
                            <Loader2 className="w-2.5 h-2.5 animate-spin mr-1" />
                            Scan
                          </Badge>
                        )}
                        {status === "complete" && (
                          <Badge
                            variant="outline"
                            withDot
                            dotColor="#10B981"
                            className="font-bold border-emerald-500/20 bg-emerald-500/[0.04] text-emerald-400 uppercase tracking-widest font-mono text-[9px]"
                          >
                            Finished
                          </Badge>
                        )}
                        {status === "unsupported" && (
                          <Badge
                            variant="outline"
                            className="text-slate-500 font-bold border-white/10 bg-white/[0.03] uppercase tracking-widest font-mono text-[9px]"
                          >
                            N/A
                          </Badge>
                        )}
                        {status === "error" && (
                          <Badge
                            variant="outline"
                            withDot
                            dotColor="#F87171"
                            className="font-bold border-rose-500/20 bg-rose-500/[0.04] text-rose-400 uppercase tracking-widest font-mono text-[9px]"
                          >
                            Error
                          </Badge>
                        )}
                      </div>
                    </div>

                    {/* ═══ BODY: state-dependent content ═══ */}

                    {/* Checking state */}
                    {status === "checking" && (
                      <div className="space-y-2.5">
                        <p className="text-xs text-amber-300/70 leading-relaxed">
                          Agent standing by — connecting to analysis pipeline…
                        </p>
                        <div className="w-full h-0.5 bg-white/[0.06] rounded-full overflow-hidden relative">
                          <div
                            className="absolute h-full w-[45%] bg-gradient-to-r from-transparent via-cyan-400/60 to-transparent rounded-full"
                            style={{
                              animation: "bar-slide 1.6s ease-in-out infinite",
                            }}
                          />
                        </div>
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

                    {/* Running state */}
                    {status === "running" && (
                      <div className="space-y-2">
                        <LiveThinkingText text={thinking} active={true} />
                        {(() => {
                          const upd = agentUpdates[agent.id];
                          const toolsTotal = upd?.tools_total ?? 0;
                          const toolsDone = upd?.tools_done ?? 0;
                          const pct =
                            toolsTotal > 0
                              ? Math.min(
                                  100,
                                  Math.round((toolsDone / toolsTotal) * 100),
                                )
                              : null;
                          return (
                            <div className="mt-2 space-y-1">
                              <div className="relative w-full h-1 bg-white/5 rounded-full overflow-hidden">
                                {pct !== null ? (
                                  <div
                                    className="h-full rounded-full"
                                    style={{
                                      width: `${pct}%`,
                                      background: "#22D3EE",
                                      boxShadow: "0 0 8px rgba(34,211,238,0.6)",
                                    }}
                                  />
                                ) : (
                                  <div
                                    className="absolute h-full w-[45%] bg-gradient-to-r from-transparent via-cyan-500/50 to-transparent rounded-full"
                                    style={{
                                      animation:
                                        "bar-slide 2s ease-in-out infinite",
                                    }}
                                  />
                                )}
                              </div>
                              {pct !== null && (
                                <div className="flex justify-between text-[9px] text-white/20 font-bold uppercase tracking-widest font-mono">
                                  <span>
                                    Units: {toolsDone}/{toolsTotal}
                                  </span>
                                  <span
                                    style={{ color: "rgba(34,211,238,0.65)" }}
                                  >
                                    {pct}%
                                  </span>
                                </div>
                              )}
                            </div>
                          );
                        })()}
                      </div>
                    )}

                    {/* ═══ COMPLETE STATE — the main redesigned section ═══ */}
                    {status === "complete" && completed && (
                      <div className="space-y-3 flex flex-col flex-1">
                        {/* Agent verdict badge */}
                        {completed.agent_verdict && (
                          <AgentVerdictBadge
                            verdict={completed.agent_verdict}
                            confidence={completed.confidence}
                          />
                        )}

                        {/* Tool findings list */}
                        {completed.findings_preview &&
                          completed.findings_preview.length > 0 && (
                            <ToolFindingsList
                              findings={completed.findings_preview}
                            />
                          )}

                        {/* Empty state when no findings */}
                        {(!completed.findings_preview ||
                          completed.findings_preview.length === 0) && (
                          <div
                            className="flex flex-col items-center justify-center p-6 rounded-2xl gap-2"
                            style={{
                              background: "rgba(255,255,255,0.02)",
                              border: "1px solid rgba(255,255,255,0.05)",
                            }}
                          >
                            <div className="w-10 h-10 rounded-full bg-emerald-500/10 flex items-center justify-center border border-emerald-500/20">
                              <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                            </div>
                            <span className="text-[11px] text-slate-400 font-mono uppercase tracking-wider text-center font-bold">
                              {completed.message ||
                                "Clearance: No Anomalies Detected"}
                            </span>
                          </div>
                        )}

                        {/* ═══ METRICS GRID ═══ */}
                        <MetricsGrid completed={completed} />
                      </div>
                    )}

                    {/* Unsupported state */}
                    {status === "unsupported" && completed && (
                      <div className="space-y-2">
                        <p className="text-xs text-slate-300/70">
                          {completed.message ||
                            completed.error ||
                            "File type not supported."}
                        </p>
                        <p className="text-[10px] text-slate-400/50 italic">
                          Not applicable for this evidence type.
                        </p>
                      </div>
                    )}

                    {/* Error state */}
                    {status === "error" && completed && (
                      <ExpandableText
                        text={completed.error || "An error occurred."}
                        className="text-rose-400"
                      />
                    )}

                    {/* Waiting state */}
                    {status === "waiting" && (
                      <p className="text-xs text-foreground/20 font-mono italic">
                        Awaiting dispatch...
                      </p>
                    )}
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>

        {/* Skipped agents */}
        {hiddenUnsupportedAgents.size > 0 && (
          <SkippedAgentsPanel hidden={hiddenUnsupportedAgents} />
        )}

        {/* Decision buttons */}
        {showInitialDecision && (
          <DecisionButtons
            variant="initial"
            isNavigating={isNavigating}
            onAcceptAnalysis={onAcceptAnalysis}
            onDeepAnalysis={onDeepAnalysis}
          />
        )}
        {showDeepComplete && (
          <DecisionButtons
            variant="deep"
            isNavigating={isNavigating}
            onNewUpload={onNewUpload}
            onViewResults={onViewResults}
            playSound={playSound}
          />
        )}

        {/* Still running */}
        {!showInitialDecision && !showDeepComplete && (
          <div className="mt-8 text-center">
            <div className="inline-flex items-center gap-2">
              {!allAgentsDone && (
                <span className="relative flex h-1.5 w-1.5 shrink-0">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-40" />
                  <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-cyan-400" />
                </span>
              )}
              <p className="text-sm font-medium text-foreground/50">
                {progressText}
              </p>
            </div>
            {!!pipelineMessage && (
              <div className="mt-3 max-w-xl mx-auto px-4 py-3 rounded-xl glass-panel border border-border-subtle">
                <LiveThinkingText
                  text={humaniseThinking(pipelineMessage, "")}
                  active={!allAgentsDone}
                />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ═══ Agent Verdict Badge ═══════════════════════════════════════════════════════

function AgentVerdictBadge({
  verdict,
  confidence,
}: {
  verdict: string;
  confidence?: number;
}) {
  const vs = VERDICT_STYLES[verdict] ?? VERDICT_STYLES.INCONCLUSIVE;
  const icon =
    verdict === "AUTHENTIC" ? (
      <CheckCircle2 className="w-4 h-4" />
    ) : verdict === "LIKELY_MANIPULATED" ? (
      <AlertTriangle className="w-4 h-4" />
    ) : (
      <div className="text-[12px] font-black leading-none">?</div>
    );

  return (
    <div
      className="flex items-center gap-3 px-4 py-3 rounded-xl overflow-hidden"
      style={{
        background: vs.bg,
        backdropFilter: "blur(12px)",
        border: `1px solid ${vs.border}`,
        boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
      }}
    >
      <div
        className={clsx(
          "w-8 h-8 rounded-lg flex items-center justify-center shrink-0 border",
          vs.text,
        )}
        style={{ background: vs.bg, borderColor: vs.border }}
      >
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-[9px] font-bold uppercase tracking-[0.2em] leading-none mb-1.5 opacity-60 text-white/40">
          Verdict
        </p>
        <Badge
          variant={vs.badge}
          size="lg"
          withDot
          className="font-black uppercase tracking-widest font-heading px-3 py-0.5 text-[10px]"
        >
          {verdict.replace(/_/g, " ")}
        </Badge>
      </div>
      {confidence !== undefined && (
        <div className="text-right shrink-0">
          <p className="text-[8px] font-mono text-slate-500 uppercase tracking-tighter font-bold">
            Confidence
          </p>
          <span
            className={clsx(
              "text-lg font-black tabular-nums font-mono drop-shadow",
              confidenceColor(confidence),
            )}
          >
            {Math.round(confidence * 100)}%
          </span>
        </div>
      )}
    </div>
  );
}

// ═══ Tool Findings List ═══════════════════════════════════════════════════════
// Shows first 2 tools, then a collapsible "Show More" for remaining.

const INITIAL_VISIBLE_TOOLS = 2;

function ToolFindingsList({ findings }: { findings: FindingPreview[] }) {
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? findings : findings.slice(0, INITIAL_VISIBLE_TOOLS);
  const remaining = findings.length - INITIAL_VISIBLE_TOOLS;

  return (
    <div className="space-y-2.5">
      {visible.map((f, i) => (
        <ToolCard key={`${f.tool}-${i}`} finding={f} />
      ))}

      {remaining > 0 && !showAll && (
        <button
          onClick={() => setShowAll(true)}
          className="w-full py-2.5 text-[10px] font-black tracking-[0.15em] uppercase text-white/40 hover:text-cyan-400 transition-all text-center
            border border-white/10 border-dashed rounded-xl hover:bg-white/[0.03] hover:border-cyan-500/20"
        >
          Show {remaining} More Tool{remaining !== 1 ? "s" : ""}
        </button>
      )}

      {showAll && findings.length > INITIAL_VISIBLE_TOOLS && (
        <button
          onClick={() => setShowAll(false)}
          className="w-full py-2 text-[10px] font-black tracking-[0.15em] uppercase text-white/30 hover:text-cyan-400 transition-all text-center"
        >
          ▲ Collapse
        </button>
      )}
    </div>
  );
}

// ═══ Metrics Grid ═════════════════════════════════════════════════════════════
// Horizontal grid: Error Rate · Confidence · Manipulation Score

function MetricsGrid({ completed }: { completed: AgentUpdate }) {
  const errorRate = completed.tool_error_rate ?? 0;
  const confidence = completed.confidence ?? 0;

  // Derive a manipulation probability from confidence + verdict
  let manipulationPct = 0;
  if (completed.agent_verdict === "LIKELY_MANIPULATED") {
    manipulationPct = Math.round((1 - confidence) * 100);
  } else if (completed.agent_verdict === "INCONCLUSIVE") {
    manipulationPct = Math.round((1 - confidence) * 50);
  } else {
    manipulationPct = Math.round((1 - confidence) * 20);
  }
  manipulationPct = Math.min(100, Math.max(0, manipulationPct));

  const errorPct = Math.round(errorRate * 100);
  const confPct = Math.round(confidence * 100);

  return (
    <div className="grid grid-cols-3 gap-2 mt-auto pt-2">
      <MetricCell
        label="Error Rate"
        value={`${errorPct}%`}
        color={errorPct <= 15 ? "emerald" : errorPct <= 30 ? "amber" : "red"}
      />
      <MetricCell
        label="Confidence"
        value={`${confPct}%`}
        color={confPct >= 75 ? "emerald" : confPct >= 50 ? "amber" : "red"}
      />
      <MetricCell
        label="Manipulation"
        value={`${manipulationPct}%`}
        color={
          manipulationPct <= 15
            ? "emerald"
            : manipulationPct <= 40
              ? "amber"
              : "red"
        }
      />
    </div>
  );
}

const METRIC_COLORS: Record<
  string,
  { text: string; bg: string; border: string }
> = {
  emerald: {
    text: "text-emerald-400",
    bg: "bg-emerald-500/8",
    border: "border-emerald-500/15",
  },
  amber: {
    text: "text-amber-400",
    bg: "bg-amber-500/8",
    border: "border-amber-500/15",
  },
  red: {
    text: "text-red-400",
    bg: "bg-red-500/8",
    border: "border-red-500/15",
  },
};

function MetricCell({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color: string;
}) {
  const c = METRIC_COLORS[color] ?? METRIC_COLORS.amber;
  return (
    <div
      className={clsx(
        "rounded-lg px-2.5 py-2 text-center border",
        c.bg,
        c.border,
      )}
    >
      <p className="text-[8px] font-mono font-bold uppercase tracking-[0.15em] text-white/30 mb-1">
        {label}
      </p>
      <p className={clsx("text-sm font-black font-mono tabular-nums", c.text)}>
        {value}
      </p>
    </div>
  );
}

// ═══ Skipped Agents Panel ═════════════════════════════════════════════════════

function SkippedAgentsPanel({ hidden }: { hidden: Set<string> }) {
  const [show, setShow] = useState(false);
  return (
    <div className="w-full max-w-5xl mt-6 flex flex-col items-center">
      <button
        onClick={() => setShow((s) => !s)}
        className="flex items-center gap-2 px-4 py-2 rounded border border-white/5 bg-white/[0.02] hover:bg-white/[0.04] transition-colors text-[10px] font-black font-mono text-white/40 uppercase tracking-[0.2em]"
      >
        <span>{hidden.size} Skipped Units (Not Applicable)</span>
        <ChevronDown
          className={clsx(
            "w-3 h-3 transition-transform duration-200",
            show && "rotate-180",
          )}
        />
      </button>
      {show && (
        <div className="overflow-hidden w-full max-w-md mt-3">
          <div className="flex flex-col gap-2 p-3 rounded-xl border border-white/[0.04] bg-white/[0.01]">
            {Array.from(hidden).map((agentId) => {
              const meta = AGENTS_DATA.find((a) => a.id === agentId);
              if (!meta) return null;
              return (
                <div
                  key={agentId}
                  className="flex items-center justify-between px-3 py-2 rounded-lg bg-white/[0.02] border border-white/[0.02]"
                >
                  <div className="flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full shrink-0 bg-cyan-400/50" />
                    <span className="text-sm text-slate-300 font-medium">
                      {meta.name}
                    </span>
                  </div>
                  <span className="text-[10px] font-black font-mono text-white/20 uppercase tracking-[0.2em]">
                    Incompatible
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ═══ Decision Buttons ══════════════════════════════════════════════════════════

function DecisionButtons(props: {
  variant: "initial" | "deep";
  isNavigating?: boolean;
  onAcceptAnalysis?: () => void;
  onDeepAnalysis?: () => void;
  onNewUpload?: () => void;
  onViewResults?: () => void;
  playSound?: (type: SoundType) => void;
}) {
  if (props.variant === "initial") {
    return (
      <div className="mt-8 w-full max-w-3xl mx-auto">
        <div className="surface-panel rounded-2xl p-5 space-y-4 shadow-[0_0_15px_rgba(34,211,238,0.1)] ring-1 ring-cyan-500/20 border border-border-bold">
          <div className="text-center space-y-1">
            <p className="text-[10px] font-black font-mono uppercase tracking-[0.3em] text-cyan-400">
              Investigator Protocol
            </p>
            <h3 className="text-lg font-black text-white font-heading uppercase tracking-tighter">
              Initial Scan Concluded
            </h3>
          </div>
          <div className="flex flex-col sm:flex-row gap-3" role="group" aria-label="Analysis decision buttons">
            <button
              onClick={props.onAcceptAnalysis}
              disabled={props.isNavigating}
              className="btn-pill-secondary flex-1 py-4 justify-center text-xs shadow-[0_0_24px_rgba(34,211,238,0.18)]"
              aria-label="Accept current analysis and compile report"
              aria-busy={props.isNavigating}
            >
              {props.isNavigating ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                  Compiling...
                </>
              ) : (
                <>
                  <FileText className="w-4 h-4" aria-hidden="true" />
                  Accept Analysis
                  <ArrowRight className="w-3.5 h-3.5 ml-1 opacity-70" aria-hidden="true" />
                </>
              )}
            </button>
            <button
              onClick={props.onDeepAnalysis}
              disabled={props.isNavigating}
              className="btn-pill-primary flex-1 py-4 justify-center text-xs relative overflow-hidden shadow-[0_0_28px_rgba(34,211,238,0.25)]"
              aria-label="Run deep analysis with additional forensic tools"
              aria-busy={props.isNavigating}
            >
              <Microscope className="w-4 h-4" aria-hidden="true" />
              Deep Analysis
              <ArrowRight className="w-3.5 h-3.5 ml-1 opacity-70" aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mt-8 w-full max-w-3xl mx-auto">
      <div className="surface-panel rounded-2xl p-5 space-y-4 shadow-[0_0_15px_rgba(34,211,238,0.1)] ring-1 ring-cyan-500/20 border border-border-bold">
        <div className="text-center space-y-1">
          <p className="text-[9px] font-mono text-emerald-500 uppercase tracking-widest font-bold">
            Verification Complete
          </p>
          <h3 className="text-base font-bold text-foreground font-heading uppercase">
            Council Arbiter Verification
          </h3>
        </div>
        <div className="flex flex-col sm:flex-row gap-3" role="group" aria-label="Post-analysis action buttons">
          <button
            onClick={() => {
              props.playSound?.("click");
              props.onNewUpload?.();
            }}
            disabled={props.isNavigating}
            className="btn-pill-secondary flex-1 py-4 justify-center text-xs"
            aria-label="Reset and start new investigation"
          >
            <RotateCcw className="w-4 h-4 opacity-40" aria-hidden="true" />
            RESET TERMINAL
          </button>
          <button
            onClick={() => {
              props.playSound?.("click");
              props.onViewResults?.();
            }}
            disabled={props.isNavigating}
            className="btn-pill-primary flex-1 py-4 justify-center text-xs relative overflow-hidden shadow-[0_0_30px_rgba(34,211,238,0.3)]"
            aria-label="View final forensic report"
            aria-busy={props.isNavigating}
          >
            {props.isNavigating ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                FINALIZING...
              </>
            ) : (
              <>
                <FileText className="w-4 h-4" aria-hidden="true" />
                ACCESS LEDGER
                <ArrowRight className="w-4 h-4 ml-1" aria-hidden="true" />
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
