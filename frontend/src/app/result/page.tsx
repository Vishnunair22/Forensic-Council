"use client";

import React, {
  useState,
  useEffect,
  useMemo,
  useRef,
  useCallback,
} from "react";
import {
  AlertTriangle,
  ShieldCheck,
  RotateCcw,
  Home,
  ChevronDown,
  Lock,
  FileText,
  Shield,
  XCircle,
  Download,
  LinkIcon,
  Fingerprint,
  Image as ImageIcon,
  Film,
  Mic,
  AlertCircle,
  Activity,
  Info,
  History,
  X,
  Zap,
  Layers,
  Clock,
  Target,
  ArrowRight,
  BarChart2,
  Award,
  Search,
  Cpu,
  Hash,
  Trash2,
} from "lucide-react";
import { useRouter } from "next/navigation";
import clsx from "clsx";
import { useForensicData, mapReportDtoToReport } from "@/hooks/useForensicData";
import { useSound } from "@/hooks/useSound";
import { type HistoryItem } from "@/components/ui/HistoryDrawer";
import {
  getReport,
  getArbiterStatus,
  type ReportDTO,
  type AgentMetricsDTO,
  type AgentFindingDTO,
} from "@/lib/api";
import { getVerdictConfig } from "@/lib/verdict";
import { AgentFindingCard } from "@/components/ui/AgentFindingCard";
import { ForensicProgressOverlay } from "@/components/ui/ForensicProgressOverlay";
import type { AgentUpdate } from "@/components/evidence/AgentProgressDisplay";
import { DeepModelTelemetry } from "@/components/result/DeepModelTelemetry";
import { TribunalMatrix } from "@/components/result/TribunalMatrix";
import { EvidenceGraph } from "@/components/result/EvidenceGraph";

const isDev = process.env.NODE_ENV !== "production";
const dbg = { error: isDev ? console.error.bind(console) : () => {} };

// ─── Constants ────────────────────────────────────────────────────────────────
const ALL_AGENT_IDS = ["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"];

const AGENT_META: Record<
  string,
  {
    name: string;
    role: string;
    accentColor: string;
    accentBg: string;
    accentBorder: string;
    accentFill: string;
  }
> = {
  Agent1: {
    name: "Image Integrity Expert",
    role: "Image Integrity",
    accentColor: "text-cyan-400",
    accentBg: "bg-cyan-500/10",
    accentBorder: "border-cyan-500/30",
    accentFill: "#22d3ee",
  },
  Agent2: {
    name: "Audio Forensics Expert",
    role: "Audio Forensics",
    accentColor: "text-indigo-400",
    accentBg: "bg-indigo-500/10",
    accentBorder: "border-indigo-500/30",
    accentFill: "#818cf8",
  },
  Agent3: {
    name: "Object & Weapon Analyst",
    role: "Object & Weapons",
    accentColor: "text-sky-400",
    accentBg: "bg-sky-500/10",
    accentBorder: "border-sky-500/30",
    accentFill: "#38bdf8",
  },
  Agent4: {
    name: "Temporal Video Analyst",
    role: "Temporal Video",
    accentColor: "text-teal-400",
    accentBg: "bg-teal-500/10",
    accentBorder: "border-teal-500/30",
    accentFill: "#2dd4bf",
  },
  Agent5: {
    name: "Metadata & Context Expert",
    role: "Metadata & Context",
    accentColor: "text-blue-400",
    accentBg: "bg-blue-500/10",
    accentBorder: "border-blue-500/30",
    accentFill: "#60a5fa",
  },
};

type Tab = "analysis" | "history";

// ─── Helpers ──────────────────────────────────────────────────────────────────
function confColor(c: number) {
  return c >= 0.75
    ? "text-emerald-400"
    : c >= 0.5
      ? "text-amber-400"
      : "text-red-400";
}

function confHex(c: number) {
  return c >= 0.75 ? "#34d399" : c >= 0.5 ? "#fbbf24" : "#f87171";
}

function fileTypeIcon(mime: string | undefined) {
  if (!mime) return FileText;
  if (mime.startsWith("image/")) return ImageIcon;
  if (mime.startsWith("video/")) return Film;
  if (mime.startsWith("audio/")) return Mic;
  return FileText;
}

function stripToolPrefix(text: string): string {
  if (!text) return text;
  const colonIdx = text.indexOf(":");
  if (colonIdx <= 0 || colonIdx > 55) return text;
  const candidate = text.slice(0, colonIdx).trim();
  const wordCount = candidate.split(/\s+/).length;
  if (wordCount <= 4 && /^[A-Z][A-Za-z0-9 /&-]{2,54}$/.test(candidate)) {
    const lower = candidate.toLowerCase();
    const skipWords = [
      "and",
      "the",
      "of",
      "for",
      "with",
      "from",
      "this",
      "that",
      "has",
      "was",
      "were",
    ];
    if (skipWords.some((w) => lower.split(/\s+/).includes(w))) return text;
    return text.slice(colonIdx + 1).trimStart();
  }
  return text;
}

const TRIVIAL_UNCERTAINTY = new Set([
  "all findings have been resolved. no significant uncertainties remain.",
  "no significant uncertainties remain.",
  "analysis complete. no uncertainties identified.",
]);
function isBoilerplateUncertainty(s: string): boolean {
  return TRIVIAL_UNCERTAINTY.has(s.toLowerCase().trim());
}

function fmtTime(iso: string) {
  try {
    return new Date(iso).toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

function fmtDuration(from: string, to: string): string {
  try {
    const ms = new Date(to).getTime() - new Date(from).getTime();
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  } catch {
    return "—";
  }
}

function fmtTimestamp(ts: number) {
  return new Date(ts).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

// ─── SVG Arc Gauge ────────────────────────────────────────────────────────────
function ArcGauge({
  pct,
  color,
  size = 72,
}: {
  pct: number;
  color: string;
  size?: number;
}) {
  const r = (size - 12) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const totalAngle = 240;
  const startAngle = 150;
  const endAngle = startAngle + totalAngle;
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const arcPath = (angle: number) => {
    const x = cx + r * Math.cos(toRad(angle));
    const y = cy + r * Math.sin(toRad(angle));
    return `${x},${y}`;
  };
  const filledAngle = startAngle + (totalAngle * Math.min(pct, 100)) / 100;

  const describeArc = (start: number, end: number) => {
    const s = arcPath(start);
    const e = arcPath(end);
    const large = end - start > 180 ? 1 : 0;
    return `M ${s} A ${r} ${r} 0 ${large} 1 ${e}`;
  };

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className="shrink-0"
      role="img"
      aria-label={`Confidence: ${pct}%`}
    >
      <title>Confidence gauge: {pct}%</title>
      <path
        d={describeArc(startAngle, endAngle)}
        fill="none"
        stroke="rgba(255,255,255,0.06)"
        strokeWidth="5"
        strokeLinecap="round"
      />
      {pct > 0 && (
        <path
          d={describeArc(startAngle, filledAngle)}
          fill="none"
          stroke={color}
          strokeWidth="5"
          strokeLinecap="round"
          opacity="0.9"
        />
      )}
    </svg>
  );
}

// ─── Evidence Thumbnail ───────────────────────────────────────────────────────
function EvidenceThumbnail({
  mime,
  thumbnail,
  size = "md",
}: {
  mime: string | null;
  thumbnail: string | null;
  size?: "sm" | "md" | "lg";
}) {
  const dim =
    size === "sm"
      ? "w-10 h-10"
      : size === "lg"
        ? "w-24 h-24 sm:w-28 sm:h-28"
        : "w-16 h-16";
  if (thumbnail) {
    return (
      /* eslint-disable-next-line @next/next/no-img-element */
      <img
        src={thumbnail}
        alt={`Evidence preview: ${mime || 'unknown type'}`}
        className={clsx(dim, "object-cover rounded-lg")}
      />
    );
  }
  const FtIcon = fileTypeIcon(mime || undefined);
  const isAudio = mime?.startsWith("audio/");
  const isVideo = mime?.startsWith("video/");
  return (
    <div
      className={clsx(
        dim,
        "flex flex-col items-center justify-center gap-1 rounded-lg",
        "bg-white/[0.03] border border-white/[0.06]",
      )}
    >
      {isAudio ? (
        <Mic className="w-5 h-5 text-emerald-400/50" />
      ) : isVideo ? (
        <Film className="w-5 h-5 text-rose-400/50" />
      ) : (
        <FtIcon className="w-5 h-5 text-amber-500/50" />
      )}
    </div>
  );
}

// ─── Section Header ───────────────────────────────────────────────────────────
function SectionHeader({
  icon,
  label,
  sub,
}: {
  icon: React.ReactNode;
  label: string;
  sub?: string;
}) {
  return (
    <div className="flex items-center gap-3 mb-5">
      <div className="w-8 h-8 rounded-xl bg-white/[0.04] border border-white/[0.08] flex items-center justify-center shrink-0">
        {icon}
      </div>
      <div>
        <h3 className="text-[11px] font-black uppercase tracking-[0.25em] text-foreground/80">
          {label}
        </h3>
        {sub && (
          <p className="text-[9px] font-mono text-foreground/25 mt-0.5">
            {sub}
          </p>
        )}
      </div>
      <div className="flex-1 h-px bg-gradient-to-r from-white/[0.06] to-transparent" />
    </div>
  );
}

// ─── Collapsible Section ──────────────────────────────────────────────────────
function CollapsibleSection({
  icon,
  title,
  count,
  color,
  children,
  defaultOpen = false,
}: {
  icon: React.ReactNode;
  title: string;
  count?: number;
  color: "emerald" | "amber" | "violet" | "amber-muted" | "rose" | "cyan";
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const colorMap: Record<string, string> = {
    emerald: "text-emerald-400",
    amber: "text-amber-500",
    violet: "text-violet-400",
    "amber-muted": "text-amber-400/60",
    rose: "text-rose-400",
    cyan: "text-cyan-400",
  };
  const bgMap: Record<string, string> = {
    emerald: "bg-emerald-500/10 border-emerald-500/20",
    amber: "bg-amber-500/10 border-amber-500/20",
    violet: "bg-violet-500/10 border-violet-500/20",
    "amber-muted": "bg-amber-500/[0.06] border-amber-500/15",
    rose: "bg-rose-500/10 border-rose-500/20",
    cyan: "bg-cyan-500/10 border-cyan-500/20",
  };

  return (
    <div
      className="rounded-2xl overflow-hidden border border-white/[0.06]"
      style={{ background: "rgba(255,255,255,0.018)" }}
    >
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={`collapsible-${title}`}
        className="w-full flex items-center justify-between px-5 py-3.5 hover:bg-white/[0.03] transition-all duration-200 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400"
      >
        <span
          className={clsx(
            "flex items-center gap-2.5 text-[10px] font-bold uppercase tracking-widest",
            colorMap[color],
          )}
        >
          {icon}
          {title}
          {count !== undefined && count > 0 ? ` (${count})` : ""}
        </span>
        <div
          className={clsx(
            "w-6 h-6 rounded-full border flex items-center justify-center transition-all duration-300",
            bgMap[color],
            open && "rotate-180",
          )}
        >
          <ChevronDown className="w-3.5 h-3.5 text-foreground/50" />
        </div>
      </button>
      {open && (
        <div
          id={`collapsible-${title}`}
          className="px-5 pb-5"
          style={{ borderTop: "1px solid rgba(255,255,255,0.05)" }}
        >
          {children}
        </div>
      )}
    </div>
  );
}

// ─── Expandable Text ──────────────────────────────────────────────────────────
function ExpandableText({
  text,
  clamp = 200,
  className,
}: {
  text: string;
  clamp?: number;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const needsClamp = text.length > clamp;
  const display =
    needsClamp && !open ? text.slice(0, clamp).trimEnd() + "…" : text;
  return (
    <div>
      <p
        id={`expandable-text-${clamp}`}
        className={clsx(
          "text-[11px] leading-relaxed whitespace-pre-wrap break-words",
          className || "text-foreground/60",
        )}
      >
        {display}
      </p>
      {needsClamp && (
        <button
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-controls={`expandable-text-${clamp}`}
          className="mt-1 text-[9px] font-bold uppercase tracking-[0.15em] text-cyan-400/60 hover:text-cyan-300 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400"
        >
          {open ? "▲ Show less" : "▼ Show more"}
        </button>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ═══════════════════════════════════════════════════════════════════════════════
type PageState = "arbiter" | "ready" | "error" | "empty";

export default function ResultPage() {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [state, setState] = useState<PageState>("arbiter");
  const [report, setReport] = useState<ReportDTO | null>(null);
  const [arbiterMsg, setArbiterMsg] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const [activeTab, setActiveTab] = useState<Tab>("analysis");
  const [isDeepPhase, setIsDeepPhase] = useState(false);
  const [thumbnail, setThumbnail] = useState<string | null>(null);
  const [mimeType, setMimeType] = useState<string | null>(null);
  const [agentTimeline, setAgentTimeline] = useState<AgentUpdate[]>([]);
  const [pipelineStartAt, setPipelineStartAt] = useState<string | null>(null);
  const historySavedRef = useRef(false);
  const historyPanelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setIsDeepPhase(sessionStorage.getItem("forensic_is_deep") === "true");
    setThumbnail(sessionStorage.getItem("forensic_thumbnail"));
    setMimeType(sessionStorage.getItem("forensic_mime_type"));
    setPipelineStartAt(sessionStorage.getItem("forensic_pipeline_start"));
    try {
      const key =
        sessionStorage.getItem("forensic_is_deep") === "true"
          ? "forensic_deep_agents"
          : "forensic_initial_agents";
      const stored = sessionStorage.getItem(key);
      if (stored) setAgentTimeline(JSON.parse(stored));
    } catch {
      /* ignore */
    }
  }, []);

  const { addToHistory } = useForensicData();
  const { playSound } = useSound();
  const soundRef = useRef(playSound);
  useEffect(() => {
    soundRef.current = playSound;
  }, [playSound]);

  // History tab dismissal via click-outside removed to allow normal tab usage

  // ── Poll arbiter then fetch report ────────────────────────────────────────
  useEffect(() => {
    const sessionId = sessionStorage.getItem("forensic_session_id");
    if (!sessionId) {
      setState("empty");
      return;
    }

    const sid = sessionId;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    let attempts = 0;
    const MAX = 150;

    async function poll() {
      if (cancelled) return;
      attempts++;
      try {
        const s = await getArbiterStatus(sid);
        if (cancelled) return;

        if (s.status === "complete" || s.status === "not_found") {
          try {
            const res = await getReport(sid);
            if (cancelled) return;
            if (res.status === "complete" && res.report) {
              setReport(res.report);
              setState("ready");
              addToHistory(mapReportDtoToReport(res.report));
              try {
                const stored = sessionStorage.getItem("fc_full_report_history");
                const hist: ReportDTO[] = stored ? JSON.parse(stored) : [];
                const snap = res.report;
                if (snap && !hist.some((r) => r.report_id === snap.report_id)) {
                  const serialised = JSON.stringify(
                    [snap, ...hist].slice(0, 20),
                  );
                  if (serialised.length < 4_000_000) {
                    sessionStorage.setItem(
                      "fc_full_report_history",
                      serialised,
                    );
                  }
                }
              } catch {
                /* ignore */
              }
              setTimeout(() => soundRef.current("arbiter_done"), 150);
              return;
            }
          } catch (e) {
            dbg.error("getReport failed:", e);
          }
        } else if (s.status === "error") {
          setErrorMsg(s.message || "Investigation failed");
          setState("error");
          return;
        } else {
          setArbiterMsg(s.message || "");
          try {
            const res = await getReport(sid);
            if (!cancelled && res.status === "complete" && res.report) {
              setReport(res.report);
              setState("ready");
              addToHistory(mapReportDtoToReport(res.report));
              setTimeout(() => soundRef.current("arbiter_done"), 150);
              return;
            }
          } catch {
            /* keep polling */
          }
        }
      } catch {
        /* network */
      }

      if (!cancelled && attempts < MAX) {
        timer = setTimeout(poll, 2000);
      } else if (!cancelled) {
        setErrorMsg("Arbiter timed out. The session may have expired.");
        setState("error");
      }
    }

    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setMounted(true);
  }, []);

  // ── Derived data ──────────────────────────────────────────────────────────
  const activeAgentIds = useMemo(() => {
    const SKIP_TYPES = new Set([
      "file type not applicable",
      "format not supported",
    ]);
    return Object.keys(report?.per_agent_findings ?? {}).filter((id) => {
      const flist = report?.per_agent_findings[id] ?? [];
      return (
        flist.length > 0 &&
        !flist.every((f) =>
          SKIP_TYPES.has(String(f.finding_type).toLowerCase()),
        )
      );
    });
  }, [report]);

  const keyFindings = useMemo(() => {
    if (report?.key_findings && report.key_findings.length > 0)
      return report.key_findings;
    const SKIP_TYPES = new Set([
      "file type not applicable",
      "format not supported",
    ]);
    const summaries: string[] = [];
    for (const id of activeAgentIds) {
      const findings = report?.per_agent_findings[id] ?? [];
      for (const f of findings) {
        if (SKIP_TYPES.has(String(f.finding_type).toLowerCase())) continue;
        const s = f.reasoning_summary?.trim();
        if (s && s.length > 10 && !summaries.includes(s)) summaries.push(s);
      }
    }
    return summaries.slice(0, 8);
  }, [report, activeAgentIds]);

  const vc = report ? getVerdictConfig(report.overall_verdict ?? "") : null;
  const confPct = Math.round((report?.overall_confidence ?? 0) * 100);
  const errPct = Math.round((report?.overall_error_rate ?? 0) * 100);
  const manipPct = Math.round((report?.manipulation_probability ?? 0) * 100);

  const fileName = useMemo(() => {
    if (typeof window === "undefined")
      return report?.case_id ?? "Evidence File";
    return (
      sessionStorage.getItem("forensic_file_name") ||
      report?.case_id ||
      "Evidence File"
    );
  }, [report]);

  // Compute total pipeline duration
  const pipelineDuration = useMemo(() => {
    if (pipelineStartAt && report?.signed_utc) {
      return fmtDuration(pipelineStartAt, report.signed_utc);
    }
    if (agentTimeline.length > 0 && pipelineStartAt) {
      const lastAgent = agentTimeline[agentTimeline.length - 1];
      if (lastAgent?.completed_at)
        return fmtDuration(pipelineStartAt, lastAgent.completed_at);
    }
    return null;
  }, [pipelineStartAt, report, agentTimeline]);

  // ── History tracking ──────────────────────────────────────────────────────
  useEffect(() => {
    if (state === "ready" && report && !historySavedRef.current) {
      historySavedRef.current = true;
      const hItem: HistoryItem = {
        sessionId: report.session_id,
        fileName:
          sessionStorage.getItem("forensic_file_name") || "Unknown File",
        verdict: report.overall_verdict || "INCONCLUSIVE",
        timestamp: Date.now(),
        type: isDeepPhase ? "Deep" : "Initial",
        thumbnail: sessionStorage.getItem("forensic_thumbnail") || undefined,
        mime: sessionStorage.getItem("forensic_mime_type") || undefined,
      };
      try {
        const stored = JSON.parse(
          localStorage.getItem("forensic_history") || "[]",
        ) as HistoryItem[];
        const filtered = stored.filter((h) => h.sessionId !== hItem.sessionId);
        localStorage.setItem(
          "forensic_history",
          JSON.stringify([hItem, ...filtered]),
        );
      } catch (e) {
        dbg.error("Failed to commit history", e);
      }
    }
  }, [state, report, isDeepPhase]);

  // ── Actions ───────────────────────────────────────────────────────────────
  const handleNew = useCallback(() => {
    playSound("click");
    [
      "forensic_session_id",
      "forensic_file_name",
      "forensic_case_id",
      "forensic_thumbnail",
    ].forEach((k) => sessionStorage.removeItem(k));
    router.push("/evidence", { scroll: true });
  }, [playSound, router]);

  const handleHome = useCallback(() => {
    playSound("click");
    router.push("/", { scroll: true });
  }, [playSound, router]);

  const handleExport = useCallback(() => {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `forensic-report-${report.report_id.slice(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [report]);

  if (!mounted) {
    return (
      <div className="min-h-screen text-foreground flex items-center justify-center px-6">
        <div className="w-full max-w-md rounded-3xl border border-white/[0.08] bg-white/[0.03] p-6 text-center backdrop-blur-xl">
          <p className="text-[11px] font-mono font-bold uppercase tracking-[0.22em] text-cyan-400/80">
            Loading Session
          </p>
          <p className="mt-3 text-sm text-foreground/55">
            Restoring the latest forensic view.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen text-foreground">
      {state === "arbiter" && (
        <ForensicProgressOverlay
          variant="council"
          title="Council deliberation"
          liveText={arbiterMsg}
          telemetryLabel="Report synthesis"
          showElapsed
        />
      )}

      {/* ═══ TAB BAR ═══════════════════════════════════════════════════════ */}
      <div
        className="w-full sticky top-[60px] z-40 transition-all duration-300"
        style={{
          background: "rgba(8,8,12,0.85)",
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
          borderBottom: "1px solid rgba(255,255,255,0.05)",
        }}
      >
        <div className="max-w-5xl mx-auto px-6 py-3 flex items-center justify-center gap-4">
          {/* Export — left */}
          <button
            onClick={handleExport}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-wider text-foreground/40 hover:text-foreground/70 border border-white/[0.07] bg-white/[0.03] hover:bg-white/[0.06] transition-all cursor-pointer"
          >
            <Download className="w-3 h-3" /> Export
          </button>

          {/* Pill tabs — center */}
          <div
            role="tablist"
            aria-label="Analysis views"
            className="flex gap-1 p-1 rounded-full"
            style={{
              background: "rgba(255,255,255,0.02)",
              border: "1px solid rgba(255,255,255,0.05)",
              boxShadow: "inset 0 2px 10px rgba(0,0,0,0.5)",
            }}
            onKeyDown={(e) => {
              const tabs = ["analysis", "history"] as Tab[];
              const currentIndex = tabs.indexOf(activeTab);
              let newIndex = currentIndex;
              if (e.key === "ArrowRight") {
                e.preventDefault();
                newIndex = (currentIndex + 1) % tabs.length;
                setActiveTab(tabs[newIndex]);
              } else if (e.key === "ArrowLeft") {
                e.preventDefault();
                newIndex = (currentIndex - 1 + tabs.length) % tabs.length;
                setActiveTab(tabs[newIndex]);
              } else if (e.key === "Home") {
                e.preventDefault();
                setActiveTab(tabs[0]);
              } else if (e.key === "End") {
                e.preventDefault();
                setActiveTab(tabs[tabs.length - 1]);
              }
            }}
          >
            {(["analysis", "history"] as Tab[]).map((tab) => (
              <button
                key={tab}
                role="tab"
                id={`tab-${tab}`}
                aria-selected={activeTab === tab}
                aria-controls={`panel-${tab}`}
                onClick={() => setActiveTab(tab)}
                className={clsx(
                  "px-5 py-2 rounded-full text-[10px] font-bold uppercase tracking-[0.18em] transition-all duration-300 cursor-pointer flex items-center gap-2",
                  activeTab === tab
                    ? "bg-cyan-500/15 text-cyan-300 border border-cyan-500/25 shadow-[0_4px_20px_rgba(34,211,238,0.15)]"
                    : "text-foreground/40 hover:text-foreground/70 hover:bg-white/[0.04] border border-transparent",
                )}
              >
                {tab === "analysis" ? (
                  <Activity className="w-3.5 h-3.5" aria-hidden="true" />
                ) : (
                  <History className="w-3.5 h-3.5" aria-hidden="true" />
                )}
                {tab === "analysis" ? "Current Analysis" : "History"}
              </button>
            ))}
          </div>

          {/* Phase label — right */}
          <div
            className={clsx(
              "text-[9px] font-mono font-bold uppercase tracking-widest px-3 py-1 rounded-full border",
              isDeepPhase
                ? "text-violet-400 border-violet-500/30 bg-violet-500/10"
                : "text-cyan-400 border-cyan-500/25 bg-cyan-500/10",
            )}
          >
            {isDeepPhase ? "Deep" : "Initial"}
          </div>
        </div>
      </div>

      {/* ═══ HISTORY TAB ═══════════════════════════════════════════════════ */}
      {activeTab === "history" && (
        <main
          ref={historyPanelRef}
          role="tabpanel"
          id="panel-history"
          aria-labelledby="tab-history"
          className="max-w-5xl mx-auto px-6 pt-8 pb-24 relative"
        >
          <HistoryPanel onDismiss={() => setActiveTab("analysis")} />
        </main>
      )}

      {/* ═══ ANALYSIS TAB ══════════════════════════════════════════════════ */}
      {activeTab === "analysis" && (
        <main
          role="tabpanel"
          id="panel-analysis"
          aria-labelledby="tab-analysis"
          className="max-w-5xl mx-auto px-6 pt-6 pb-16 space-y-6"
        >
          {/* Arbiter loading */}
          {state === "arbiter" && (
            <div className="flex flex-col items-center justify-center min-h-[60vh] gap-6 text-center">
              <div className="w-16 h-16 rounded-2xl flex items-center justify-center bg-white/[0.03] border border-white/[0.06]">
                <Activity className="w-7 h-7 text-amber-400 animate-pulse" />
              </div>
              <p className="text-foreground/40 text-sm font-medium font-mono">
                Council deliberating…
              </p>
            </div>
          )}

          {/* Error */}
          {state === "error" && (
            <div className="flex flex-col items-center justify-center min-h-[60vh] gap-8 text-center">
              <div className="w-20 h-20 rounded-2xl flex items-center justify-center bg-white/[0.03] border border-white/[0.06]">
                <XCircle className="w-10 h-10 text-rose-500" />
              </div>
              <div className="space-y-2">
                <h2 className="text-2xl font-bold text-foreground uppercase tracking-tight">
                  Analysis Interrupted
                </h2>
                <p className="text-foreground/40 text-sm max-w-sm font-medium">
                  {errorMsg || "An unexpected error occurred during synthesis."}
                </p>
              </div>
              <div className="flex gap-3">
                <button
                  onClick={handleNew}
                  className="btn-pill-primary text-xs"
                >
                  <RotateCcw className="w-4 h-4" /> New Analysis
                </button>
                <button
                  onClick={handleHome}
                  className="btn-pill-secondary text-xs"
                >
                  <Home className="w-4 h-4" /> Back to Home
                </button>
              </div>
            </div>
          )}

          {/* Empty */}
          {state === "empty" && (
            <div className="flex flex-col items-center justify-center min-h-[60vh] gap-8 text-center">
              <div className="w-20 h-20 rounded-2xl flex items-center justify-center bg-white/[0.03] border border-white/[0.06]">
                <FileText className="w-10 h-10 text-foreground/20" />
              </div>
              <div className="space-y-2">
                <h2 className="text-2xl font-bold text-foreground uppercase tracking-tight">
                  Null Session
                </h2>
                <p className="text-foreground/40 text-sm max-w-sm font-medium">
                  No active forensic stream detected. Please return to the
                  terminal.
                </p>
              </div>
              <div className="flex gap-3">
                <button
                  onClick={handleNew}
                  className="btn-pill-primary text-xs"
                >
                  <Search className="w-4 h-4" /> New Investigation
                </button>
                <button
                  onClick={handleHome}
                  className="btn-pill-secondary text-xs"
                >
                  <Home className="w-4 h-4" /> Back to Home
                </button>
              </div>
            </div>
          )}

          {/* ══ READY ════════════════════════════════════════════════════ */}
          {state === "ready" && report && vc && (
            <div className="space-y-6">
              {/* Degradation Warning */}
              {report.degradation_flags &&
                report.degradation_flags.length > 0 && (
                  <div className="rounded-2xl border border-amber-500/40 bg-amber-500/[0.07] p-4 flex items-start gap-3">
                    <AlertCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                    <div>
                      <p className="text-[9px] font-black font-mono uppercase tracking-[0.25em] text-amber-400 mb-1.5">
                        Degraded Analysis Mode
                      </p>
                      <ul className="space-y-0.5">
                        {report.degradation_flags.map((f, i) => (
                          <li
                            key={i}
                            className="text-[11px] text-amber-300/70 font-mono leading-relaxed"
                          >
                            • {f}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}

              {/* ══════════════════════════════════════════════════════════ */}
              {/* 1. FILE THUMBNAIL + NAME + STAGE                         */}
              {/* ══════════════════════════════════════════════════════════ */}
              <div className="rounded-2xl overflow-hidden glass-panel">
                <div className="flex items-stretch">
                  <div
                    className="w-24 sm:w-28 shrink-0 relative overflow-hidden"
                    style={{
                      background: "rgba(0,0,0,0.3)",
                      borderRight: "1px solid rgba(255,255,255,0.06)",
                    }}
                  >
                    <EvidenceThumbnail
                      mime={mimeType}
                      thumbnail={thumbnail}
                      size="lg"
                    />
                    <div
                      className={clsx(
                        "absolute bottom-0 left-0 right-0 h-[3px]",
                        isDeepPhase
                          ? "bg-gradient-to-r from-violet-500 to-purple-600"
                          : "bg-gradient-to-r from-cyan-500 to-blue-500",
                      )}
                    />
                  </div>
                  <div className="flex-1 min-w-0 p-5 flex flex-col justify-center">
                    <div className="space-y-3">
                      <p className="flex items-center gap-2 text-[8px] font-mono font-bold uppercase tracking-[0.3em] text-foreground/30">
                        Evidence File
                        <span
                          className={clsx(
                            "px-2 py-0.5 rounded border tracking-widest text-[7px]",
                            isDeepPhase
                              ? "text-violet-300 bg-violet-500/10 border-violet-500/20"
                              : "text-cyan-300 bg-cyan-500/10 border-cyan-500/20",
                          )}
                        >
                          {isDeepPhase ? "Deep Phase" : "Initial Phase"}
                        </span>
                      </p>
                      <h1 className="text-xl font-black text-foreground truncate leading-tight">
                        {fileName}
                      </h1>
                      <p className="text-[10px] font-mono text-foreground/40">
                        {mimeType || "Unknown format"}
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              {/* ══════════════════════════════════════════════════════════ */}
              {/* 1.5. VERDICT AND TIMELINE SUMMARY                        */}
              {/* ══════════════════════════════════════════════════════════ */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div
                  className={clsx(
                    "sm:col-span-2 rounded-2xl p-6 flex items-center justify-between relative overflow-hidden glass-panel border shadow-lg",
                    vc.color === "emerald"
                      ? "border-emerald-500/30 shadow-[0_4px_30px_rgba(52,211,153,0.15)]"
                      : vc.color === "red"
                        ? "border-red-500/30 shadow-[0_4px_30px_rgba(239,68,68,0.15)]"
                        : "border-amber-500/30 shadow-[0_4px_30px_rgba(245,158,11,0.15)]",
                  )}
                >
                  <div
                    className={clsx(
                      "absolute inset-0 opacity-[0.03]",
                      vc.color === "emerald"
                        ? "bg-emerald-500"
                        : vc.color === "red"
                          ? "bg-red-500"
                          : "bg-amber-500",
                    )}
                  />
                  <div className="relative z-10 space-y-1.5">
                    <p className="text-[9px] font-bold uppercase tracking-widest text-foreground/40">
                      Final Analysis Verdict
                    </p>
                    <p
                      className={clsx(
                        "text-2xl sm:text-3xl font-black uppercase tracking-tight",
                        vc.color === "emerald"
                          ? "text-emerald-400"
                          : vc.color === "red"
                            ? "text-red-400"
                            : "text-amber-400",
                      )}
                    >
                      {vc.label}
                    </p>
                  </div>
                  <div
                    className={clsx(
                      "relative z-10 w-16 h-16 rounded-[1.25rem] flex items-center justify-center border",
                      vc.color === "emerald"
                        ? "bg-emerald-500/10 border-emerald-500/20"
                        : vc.color === "red"
                          ? "bg-red-500/10 border-red-500/20"
                          : "bg-amber-500/10 border-amber-500/20",
                    )}
                  >
                    <vc.Icon
                      className={clsx(
                        "w-8 h-8",
                        vc.color === "emerald"
                          ? "text-emerald-400"
                          : vc.color === "red"
                            ? "text-red-400"
                            : "text-amber-400",
                      )}
                    />
                  </div>
                </div>

                <div className="rounded-2xl p-5 flex flex-col justify-center gap-4 glass-panel relative overflow-hidden border border-white/[0.04]">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5 text-foreground/50">
                      <Cpu className="w-3.5 h-3.5" />
                      <span className="text-[9px] font-bold uppercase tracking-widest">
                        Agents
                      </span>
                    </div>
                    <span className="text-sm font-black font-mono text-foreground/80">
                      {activeAgentIds.length}
                      <span className="text-foreground/30 font-medium">
                        /{ALL_AGENT_IDS.length}
                      </span>
                    </span>
                  </div>
                  <div className="h-px bg-white/[0.05] w-full" />
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5 text-foreground/50">
                      <Clock className="w-3.5 h-3.5" />
                      <span className="text-[9px] font-bold uppercase tracking-widest">
                        Duration
                      </span>
                    </div>
                    <span className="text-sm font-black font-mono text-cyan-400">
                      {pipelineDuration || "—"}
                    </span>
                  </div>
                </div>
              </div>

              {/* ══════════════════════════════════════════════════════════ */}
              {/* 2. CONFIDENCE / ERROR RATE / MANIPULATION SCORE          */}
              {/* ══════════════════════════════════════════════════════════ */}
              <div className="grid grid-cols-3 gap-4">
                {(() => {
                  const clr = confHex(confPct / 100);
                  return (
                    <div className="rounded-2xl p-5 flex flex-col items-center gap-3 relative overflow-hidden glass-panel">
                      <div
                        className="absolute inset-0 opacity-[0.03]"
                        style={{
                          background: `radial-gradient(circle at 50% 0%, ${clr}, transparent 70%)`,
                        }}
                      />
                      <p className="text-[8px] font-mono font-bold uppercase tracking-[0.22em] text-foreground/30 self-start">
                        Confidence
                      </p>
                      <div className="relative flex items-center justify-center">
                        <ArcGauge pct={confPct} color={clr} size={80} />
                        <div className="absolute inset-0 flex flex-col items-center justify-center">
                          <span
                            className="text-xl font-black tabular-nums"
                            style={{ color: clr }}
                          >
                            {confPct}
                          </span>
                          <span className="text-[9px] font-mono text-foreground/30">
                            %
                          </span>
                        </div>
                      </div>
                      {report.confidence_min !== undefined &&
                        report.confidence_max !== undefined && (
                          <div className="w-full space-y-1.5">
                            <div className="relative h-1 bg-white/[0.06] rounded-full overflow-hidden">
                              <div
                                className="absolute h-full rounded-full"
                                style={{
                                  background: clr,
                                  left: `${Math.round((report.confidence_min ?? 0) * 100)}%`,
                                  right: `${100 - Math.round((report.confidence_max ?? 0) * 100)}%`,
                                  opacity: 0.4,
                                }}
                              />
                              <div
                                className="absolute top-[-2px] w-1 h-[6px] rounded-full"
                                style={{
                                  background: clr,
                                  left: `${confPct}%`,
                                  transform: "translateX(-50%)",
                                }}
                              />
                            </div>
                            <p className="text-[8px] font-mono text-foreground/20 text-center">
                              {Math.round((report.confidence_min ?? 0) * 100)}–
                              {Math.round((report.confidence_max ?? 0) * 100)}%
                              range
                            </p>
                          </div>
                        )}
                    </div>
                  );
                })()}

                {(() => {
                  const clr = confHex(1 - errPct / 100);
                  const totalT = activeAgentIds.reduce(
                    (s, id) =>
                      s +
                      (report.per_agent_metrics?.[id]?.total_tools_called ?? 0),
                    0,
                  );
                  const failedT = activeAgentIds.reduce(
                    (s, id) =>
                      s + (report.per_agent_metrics?.[id]?.tools_failed ?? 0),
                    0,
                  );
                  const naT = activeAgentIds.reduce(
                    (s, id) =>
                      s +
                      (report.per_agent_metrics?.[id]?.tools_not_applicable ??
                        0),
                    0,
                  );
                  const ranT = totalT - naT - failedT;
                  return (
                    <div className="rounded-2xl p-5 flex flex-col items-center gap-3 relative overflow-hidden glass-panel">
                      <div
                        className="absolute inset-0 opacity-[0.03]"
                        style={{
                          background: `radial-gradient(circle at 50% 0%, ${clr}, transparent 70%)`,
                        }}
                      />
                      <p className="text-[8px] font-mono font-bold uppercase tracking-[0.22em] text-foreground/30 self-start">
                        Error Rate
                      </p>
                      <div className="relative flex items-center justify-center">
                        <ArcGauge pct={errPct} color={clr} size={80} />
                        <div className="absolute inset-0 flex flex-col items-center justify-center">
                          <span
                            className="text-xl font-black tabular-nums"
                            style={{ color: clr }}
                          >
                            {errPct}
                          </span>
                          <span className="text-[9px] font-mono text-foreground/30">
                            %
                          </span>
                        </div>
                      </div>
                      <div className="w-full flex items-center justify-center gap-3 text-[8px] font-mono">
                        <span className="text-emerald-400/70">{ranT} ran</span>
                        {failedT > 0 && (
                          <span className="text-amber-400/70">
                            {failedT} fail
                          </span>
                        )}
                        {naT > 0 && (
                          <span className="text-foreground/25">{naT} n/a</span>
                        )}
                      </div>
                    </div>
                  );
                })()}

                {(() => {
                  const clr =
                    manipPct >= 70
                      ? "#f87171"
                      : manipPct >= 40
                        ? "#fbbf24"
                        : "#34d399";
                  const label =
                    manipPct >= 70 ? "High" : manipPct >= 40 ? "Medium" : "Low";
                  return (
                    <div className="rounded-2xl p-5 flex flex-col items-center gap-3 relative overflow-hidden glass-panel">
                      <div
                        className="absolute inset-0 opacity-[0.03]"
                        style={{
                          background: `radial-gradient(circle at 50% 0%, ${clr}, transparent 70%)`,
                        }}
                      />
                      <p className="text-[8px] font-mono font-bold uppercase tracking-[0.22em] text-foreground/30 self-start">
                        Manipulation
                      </p>
                      <div className="relative flex items-center justify-center">
                        <ArcGauge pct={manipPct} color={clr} size={80} />
                        <div className="absolute inset-0 flex flex-col items-center justify-center">
                          <span
                            className="text-xl font-black tabular-nums"
                            style={{ color: clr }}
                          >
                            {manipPct}
                          </span>
                          <span className="text-[9px] font-mono text-foreground/30">
                            %
                          </span>
                        </div>
                      </div>
                      <div className="w-full">
                        <div className="h-1 bg-white/[0.06] rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all duration-700"
                            style={{ width: `${manipPct}%`, background: clr }}
                          />
                        </div>
                        <p
                          className="text-[8px] font-mono text-center mt-1.5"
                          style={{ color: clr }}
                        >
                          {label} Risk
                        </p>
                      </div>
                    </div>
                  );
                })()}
              </div>

              {/* ══════════════════════════════════════════════════════════ */}
              {/* 3. KEY FINDINGS                                         */}
              {/* ══════════════════════════════════════════════════════════ */}
              {(report.verdict_sentence || report.executive_summary) && (
                <div className="rounded-2xl overflow-hidden glass-panel">
                  <div
                    className="px-5 py-3.5 flex items-center gap-3"
                    style={{
                      borderBottom: "1px solid rgba(255,255,255,0.05)",
                      background: "rgba(255,255,255,0.02)",
                    }}
                  >
                    <Award className="w-4 h-4 text-amber-400/70 shrink-0" />
                    <p className="text-[10px] font-bold uppercase tracking-widest text-foreground/60">
                      Key Findings
                    </p>
                  </div>
                  <div className="p-5 space-y-4">
                    {report.verdict_sentence && (
                      <div className="flex items-start gap-3">
                        <div
                          className="w-1 h-full self-stretch rounded-full bg-amber-500/40 shrink-0 mt-0.5"
                          style={{ minHeight: "20px" }}
                        />
                        <p className="text-sm font-semibold text-foreground/80 leading-relaxed">
                          {report.verdict_sentence}
                        </p>
                      </div>
                    )}
                    {report.reliability_note && (
                      <div
                        className="flex items-center gap-2.5 p-3 rounded-xl"
                        style={{
                          background: "rgba(255,255,255,0.03)",
                          border: "1px solid rgba(255,255,255,0.06)",
                        }}
                      >
                        <Info className="w-3.5 h-3.5 text-foreground/30 shrink-0" />
                        <p className="text-[10px] font-mono text-foreground/40 leading-relaxed">
                          {report.reliability_note}
                        </p>
                      </div>
                    )}
                    {report.executive_summary && (
                      <ExpandableText
                        text={report.executive_summary}
                        clamp={400}
                        className="text-foreground/55"
                      />
                    )}
                    {keyFindings.length > 0 && (
                      <div className="grid gap-2 pt-2 border-t border-white/[0.04]">
                        {keyFindings.map((f, i) => (
                          <div
                            key={i}
                            className="flex items-start gap-3 p-3 rounded-xl transition-colors hover:bg-white/[0.02]"
                            style={{
                              background: "rgba(255,255,255,0.015)",
                              border: "1px solid rgba(255,255,255,0.05)",
                            }}
                          >
                            <span className="w-5 h-5 rounded-md bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center shrink-0 text-[8px] font-black font-mono text-emerald-400">
                              {i + 1}
                            </span>
                            <p className="text-[11px] text-foreground/65 leading-relaxed font-medium flex-1">
                              {stripToolPrefix(f)}
                            </p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* ══════════════════════════════════════════════════════════ */}
              {/* 4. ANALYSIS METADATA                                    */}
              {/* ══════════════════════════════════════════════════════════ */}
              <div className="rounded-2xl overflow-hidden glass-panel">
                <div
                  className="px-5 py-3.5"
                  style={{
                    borderBottom: "1px solid rgba(255,255,255,0.05)",
                    background: "rgba(255,255,255,0.02)",
                  }}
                >
                  <SectionHeader
                    icon={<Hash className="w-3.5 h-3.5 text-foreground/40" />}
                    label="Analysis Metadata"
                  />
                </div>
                <div className="p-5">
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {(
                      [
                        {
                          label: "Report ID",
                          value: report.report_id,
                          mono: true,
                          truncate: true,
                          icon: <Hash className="w-3 h-3" />,
                        },
                        {
                          label: "Session ID",
                          value: report.session_id,
                          mono: true,
                          truncate: true,
                          icon: <Hash className="w-3 h-3" />,
                        },
                        {
                          label: "Case ID",
                          value: report.case_id,
                          mono: false,
                          icon: <FileText className="w-3 h-3" />,
                        },
                        {
                          label: "Signed UTC",
                          value: report.signed_utc
                            ? new Date(report.signed_utc).toLocaleString()
                            : "Pending",
                          icon: <Clock className="w-3 h-3" />,
                        },
                        {
                          label: "Active Agents",
                          value: `${report.applicable_agent_count ?? activeAgentIds.length} of ${ALL_AGENT_IDS.length}`,
                          icon: <Cpu className="w-3 h-3" />,
                        },
                        {
                          label: "Calibration",
                          value: (() => {
                            const allF = Object.values(
                              report.per_agent_findings ?? {},
                            ).flat();
                            return allF.find((f) => f.calibrated)
                              ? "Platt Scaling Applied"
                              : "Uncalibrated";
                          })(),
                          icon: <Target className="w-3 h-3" />,
                        },
                        {
                          label: "SHA-256 Hash",
                          value: report.report_hash,
                          mono: true,
                          truncate: true,
                          icon: <ShieldCheck className="w-3 h-3" />,
                        },
                        {
                          label: "ECDSA Signature",
                          value: report.cryptographic_signature,
                          mono: true,
                          truncate: true,
                          icon: <Fingerprint className="w-3 h-3" />,
                        },
                        {
                          label: "Degradation",
                          value: report.degradation_flags?.length
                            ? `${report.degradation_flags.length} warning(s)`
                            : "None",
                          icon: <AlertCircle className="w-3 h-3" />,
                        },
                        ...(report.analysis_coverage_note
                          ? [
                              {
                                label: "Coverage",
                                value: report.analysis_coverage_note,
                                icon: <BarChart2 className="w-3 h-3" />,
                              },
                            ]
                          : []),
                      ] as {
                        label: string;
                        value: string | undefined;
                        mono?: boolean;
                        truncate?: boolean;
                        icon: React.ReactNode;
                      }[]
                    ).map(({ label, value, mono, truncate, icon }) => (
                      <div
                        key={label}
                        className="p-3.5 rounded-xl space-y-1.5 bg-white/[0.02] border border-white/[0.05] shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]"
                      >
                        <div className="flex items-center gap-1.5 text-[8px] font-mono font-bold uppercase tracking-[0.18em] text-foreground/25">
                          {icon}
                          {label}
                        </div>
                        <p
                          className={clsx(
                            "text-[10px] leading-relaxed",
                            mono
                              ? "font-mono text-foreground/45"
                              : "font-medium text-foreground/60",
                            truncate && "truncate",
                          )}
                          title={value || "—"}
                        >
                          {value || "—"}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {isDeepPhase && <DeepModelTelemetry report={report} />}

              {/* ══════════════════════════════════════════════════════════ */}
              {/* 5. INDIVIDUAL AGENT ANALYSIS                            */}
              {/* ══════════════════════════════════════════════════════════ */}
              <div className="space-y-3">
                <SectionHeader
                  icon={<Activity className="w-3.5 h-3.5 text-amber-400" />}
                  label="Individual Agent Analysis"
                  sub={`${activeAgentIds.length} specialist agents — full drill-down`}
                />

                {/* Summary table */}
                <div
                  className="rounded-2xl overflow-hidden"
                  style={{
                    background: "rgba(255,255,255,0.025)",
                    border: "1px solid rgba(255,255,255,0.07)",
                  }}
                >
                  <div className="overflow-x-auto">
                    <table className="w-full text-[10px]">
                      <caption className="sr-only">Agent Analysis Summary</caption>
                      <thead>
                        <tr
                          className="text-[8px] font-mono uppercase tracking-[0.18em] text-foreground/25"
                          style={{
                            borderBottom: "1px solid rgba(255,255,255,0.05)",
                            background: "rgba(255,255,255,0.02)",
                          }}
                        >
                          <th className="text-left px-4 py-3 font-bold">
                            Agent
                          </th>
                          <th className="text-left px-4 py-3 font-bold">
                            Role
                          </th>
                          <th className="text-center px-3 py-3 font-bold">
                            Tools
                          </th>
                          <th className="text-center px-3 py-3 font-bold">
                            Findings
                          </th>
                          <th className="text-center px-3 py-3 font-bold">
                            Confidence
                          </th>
                          <th className="text-center px-3 py-3 font-bold">
                            Error Rate
                          </th>
                          <th className="text-center px-3 py-3 font-bold">
                            Status
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {ALL_AGENT_IDS.map((id) => {
                          const meta = AGENT_META[id];
                          const m = report.per_agent_metrics?.[id];
                          const s = report.per_agent_summary?.[id];
                          const isActive = activeAgentIds.includes(id);
                          const toolsOk = m?.tools_succeeded ?? 0;
                          const toolsAll = m?.total_tools_called ?? 0;
                          const findings = s?.findings ?? m?.finding_count ?? 0;
                          const confPctA = Math.round(
                            (m?.confidence_score ?? 0) * 100,
                          );
                          const errRate = m
                            ? Math.round(
                                (m.tools_failed /
                                  Math.max(
                                    1,
                                    m.total_tools_called -
                                      (m.tools_not_applicable ?? 0),
                                  )) *
                                  100,
                              )
                            : 0;
                          const verdict = s?.verdict ?? null;
                          const vCfg = verdict
                            ? getVerdictConfig(verdict)
                            : null;

                          return (
                            <tr
                              key={id}
                              className={clsx(
                                "transition-all duration-150",
                                isActive
                                  ? "hover:bg-white/[0.02]"
                                  : "opacity-30",
                              )}
                              style={{
                                borderBottom:
                                  "1px solid rgba(255,255,255,0.03)",
                              }}
                            >
                              <td className="px-4 py-3">
                                <div className="flex items-center gap-2">
                                  <div
                                    className={clsx(
                                      "w-2 h-2 rounded-full shrink-0",
                                      isActive ? "" : "bg-white/10",
                                    )}
                                    style={
                                      isActive
                                        ? { background: meta.accentFill }
                                        : undefined
                                    }
                                  />
                                  <span
                                    className={clsx(
                                      "font-bold",
                                      isActive
                                        ? meta.accentColor
                                        : "text-foreground/35",
                                    )}
                                  >
                                    {meta.name}
                                  </span>
                                </div>
                              </td>
                              <td className="px-4 py-3 font-mono text-[9px] text-foreground/35">
                                {meta.role}
                              </td>
                              <td className="px-3 py-3 text-center font-mono">
                                {isActive ? (
                                  <>
                                    <span className="text-foreground/60">
                                      {toolsOk}
                                    </span>
                                    <span className="text-foreground/20">
                                      /{toolsAll}
                                    </span>
                                  </>
                                ) : (
                                  <span className="text-foreground/15">—</span>
                                )}
                              </td>
                              <td className="px-3 py-3 text-center font-mono text-foreground/55">
                                {isActive ? (
                                  findings
                                ) : (
                                  <span className="text-foreground/15">—</span>
                                )}
                              </td>
                              <td className="px-3 py-3 text-center">
                                {isActive ? (
                                  <span
                                    className={clsx(
                                      "font-black tabular-nums",
                                      confColor(confPctA / 100),
                                    )}
                                  >
                                    {confPctA}%
                                  </span>
                                ) : (
                                  <span className="text-foreground/15 font-mono">
                                    —
                                  </span>
                                )}
                              </td>
                              <td className="px-3 py-3 text-center">
                                {isActive ? (
                                  <span
                                    className={clsx(
                                      "font-mono font-bold",
                                      errRate <= 15
                                        ? "text-emerald-400"
                                        : errRate <= 30
                                          ? "text-amber-400"
                                          : "text-red-400",
                                    )}
                                  >
                                    {errRate}%
                                  </span>
                                ) : (
                                  <span className="text-foreground/15 font-mono">
                                    —
                                  </span>
                                )}
                              </td>
                              <td className="px-3 py-3 text-center">
                                {isActive && vCfg ? (
                                  <span
                                    className={clsx(
                                      "text-[8px] font-black uppercase tracking-wider",
                                      vCfg.textColor,
                                    )}
                                  >
                                    {vCfg.label}
                                  </span>
                                ) : !isActive ? (
                                  <span className="text-[8px] font-mono text-foreground/20 uppercase">
                                    Skipped
                                  </span>
                                ) : (
                                  <span className="text-foreground/20">—</span>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Detailed agent cards */}
                <div className="space-y-3 mt-4">
                  {ALL_AGENT_IDS.map((agentId) => {
                    const findings = report.per_agent_findings?.[agentId] ?? [];
                    if (findings.length === 0) return null;
                    const metrics = report.per_agent_metrics?.[agentId];
                    const narrative =
                      report.per_agent_analysis?.[agentId] ?? "";
                    const initialF = findings.filter(
                      (f) =>
                        (((f.metadata as Record<string, unknown>)
                          ?.analysis_phase as string) ?? "initial") ===
                        "initial",
                    );
                    const deepF = findings.filter(
                      (f) =>
                        (f.metadata as Record<string, unknown>)
                          ?.analysis_phase === "deep",
                    );
                    return (
                      <AgentFindingCard
                        key={agentId}
                        agentId={agentId}
                        initialFindings={initialF as AgentFindingDTO[]}
                        deepFindings={deepF as AgentFindingDTO[]}
                        metrics={metrics as AgentMetricsDTO}
                        narrative={narrative}
                        phase={
                          isDeepPhase && deepF.length > 0 ? "deep" : "initial"
                        }
                      />
                    );
                  })}
                </div>
              </div>

              {/* ══════════════════════════════════════════════════════════ */}
              {/* 6. ANALYSIS TIMELINE (Gantt-style)                      */}
              {/* ══════════════════════════════════════════════════════════ */}
              <div
                className="rounded-2xl overflow-hidden"
                style={{
                  background: "rgba(255,255,255,0.025)",
                  border: "1px solid rgba(255,255,255,0.07)",
                }}
              >
                <div
                  className="px-5 py-3.5"
                  style={{
                    borderBottom: "1px solid rgba(255,255,255,0.05)",
                    background: "rgba(255,255,255,0.02)",
                  }}
                >
                  <SectionHeader
                    icon={<Clock className="w-3.5 h-3.5 text-cyan-400/70" />}
                    label="Analysis Timeline"
                    sub="Agent & tool execution waterfall"
                  />
                </div>
                <div className="p-5">
                  {/* Vertical timeline */}
                  <div className="relative">
                    <div className="absolute left-[19px] top-4 bottom-4 w-px bg-gradient-to-b from-white/10 via-white/[0.06] to-transparent" />
                    <div className="space-y-3">
                      {/* Pipeline start */}
                      {pipelineStartAt && (
                        <TimelineEntry
                          icon={<Zap className="w-4 h-4 text-cyan-400" />}
                          accentBg="rgba(34,211,238,0.1)"
                          accentBorder="rgba(34,211,238,0.25)"
                          label="Pipeline Initiated"
                          labelColor="text-cyan-400"
                          timestamp={fmtTime(pipelineStartAt)}
                          detail="Investigation session started"
                        />
                      )}

                      {/* Agent entries */}
                      {agentTimeline.length > 0
                        ? agentTimeline.map((agent, idx) => {
                            const meta = AGENT_META[agent.agent_id] ?? {
                              accentColor: "text-foreground/50",
                              accentFill: "#ffffff",
                              name: agent.agent_name,
                              role: "",
                            };
                            const prevAgent = agentTimeline[idx - 1];
                            const duration =
                              agent.completed_at && prevAgent?.completed_at
                                ? fmtDuration(
                                    prevAgent.completed_at,
                                    agent.completed_at,
                                  )
                                : agent.completed_at &&
                                    pipelineStartAt &&
                                    idx === 0
                                  ? fmtDuration(
                                      pipelineStartAt,
                                      agent.completed_at,
                                    )
                                  : null;
                            return (
                              <TimelineEntry
                                key={agent.agent_id}
                                icon={
                                  <Cpu
                                    className="w-4 h-4"
                                    style={{ color: meta.accentFill }}
                                  />
                                }
                                accentBg={`${meta.accentFill}15`}
                                accentBorder={`${meta.accentFill}30`}
                                label={`${meta.name}`}
                                labelColor={meta.accentColor}
                                timestamp={
                                  agent.completed_at
                                    ? fmtTime(agent.completed_at)
                                    : undefined
                                }
                                detail={`${agent.tools_ran ?? 0} tools · ${agent.findings_count ?? 0} findings`}
                                duration={duration}
                                badge={agent.status}
                                confidence={agent.confidence}
                              />
                            );
                          })
                        : ALL_AGENT_IDS.map((id) => {
                            const meta = AGENT_META[id];
                            const m = report.per_agent_metrics?.[id];
                            const isAct = activeAgentIds.includes(id);
                            if (!m && !isAct) return null;
                            return (
                              <TimelineEntry
                                key={id}
                                icon={
                                  <Cpu
                                    className="w-4 h-4"
                                    style={{
                                      color: meta.accentFill,
                                      opacity: isAct ? 1 : 0.3,
                                    }}
                                  />
                                }
                                accentBg={`${meta.accentFill}${isAct ? "15" : "08"}`}
                                accentBorder={`${meta.accentFill}${isAct ? "30" : "15"}`}
                                label={meta.name}
                                labelColor={
                                  isAct
                                    ? meta.accentColor
                                    : "text-foreground/25"
                                }
                                detail={
                                  isAct && m
                                    ? `${m.tools_succeeded} tools · ${m.finding_count} findings`
                                    : undefined
                                }
                                badge={isAct ? "complete" : "skipped"}
                                confidence={
                                  isAct && m ? m.confidence_score : undefined
                                }
                              />
                            );
                          })}

                      {/* Arbiter */}
                      <TimelineEntry
                        icon={<Shield className="w-4 h-4 text-amber-400" />}
                        accentBg="rgba(245,158,11,0.12)"
                        accentBorder="rgba(245,158,11,0.28)"
                        label="Council Arbiter"
                        labelColor="text-amber-400"
                        timestamp={
                          report.signed_utc
                            ? fmtTime(report.signed_utc)
                            : undefined
                        }
                        detail={`Deliberation complete · ${report.overall_verdict}`}
                        badge="signed"
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* ══════════════════════════════════════════════════════════ */}
              {/* 7. CORROBORATING EVIDENCE                               */}
              {/* ══════════════════════════════════════════════════════════ */}
              {((report.cross_modal_confirmed?.length ?? 0) > 0 ||
                (report.contested_findings?.length ?? 0) > 0 ||
                (report.tribunal_resolved?.length ?? 0) > 0) && (
                <div className="space-y-4">
                  {isDeepPhase ? (
                    <>
                      <EvidenceGraph report={report} />
                      <TribunalMatrix report={report} />
                    </>
                  ) : (
                    <>
                      <SectionHeader
                        icon={
                          <LinkIcon className="w-3.5 h-3.5 text-foreground/40" />
                        }
                        label="Corroborating Evidence"
                      />
                      {(report.cross_modal_confirmed?.length ?? 0) > 0 && (
                        <CollapsibleSection
                          icon={<LinkIcon className="w-3.5 h-3.5" />}
                          title="Cross-Modal Confirmations"
                          count={report.cross_modal_confirmed?.length}
                          color="emerald"
                        >
                          <div className="pt-4 divide-y divide-white/[0.04]">
                            {(
                              report.cross_modal_confirmed as ReportDTO["cross_modal_confirmed"]
                            )
                              .slice(0, 10)
                              .map((f, i) => (
                                <div
                                  key={f.finding_id || i}
                                  className="flex items-start gap-3 py-3"
                                >
                                  <div className="w-1.5 h-1.5 mt-1.5 rounded-full bg-emerald-500 shrink-0" />
                                  <span className="text-[11px] text-foreground/65 leading-relaxed">
                                    {f.reasoning_summary || f.finding_type}
                                  </span>
                                </div>
                              ))}
                          </div>
                        </CollapsibleSection>
                      )}
                      {(report.contested_findings?.length ?? 0) > 0 && (
                        <CollapsibleSection
                          icon={<AlertTriangle className="w-3.5 h-3.5" />}
                          title="Contested Findings"
                          count={report.contested_findings?.length}
                          color="amber"
                        >
                          <div className="pt-4 divide-y divide-white/[0.04]">
                            {report.contested_findings.map((f, i) => (
                              <div key={i} className="py-3">
                                <p className="text-[11px] text-foreground/55 font-mono leading-relaxed">
                                  {String(
                                    (f as Record<string, unknown>)
                                      .plain_description ??
                                      "Conflicting findings — manual review required.",
                                  )}
                                </p>
                              </div>
                            ))}
                          </div>
                        </CollapsibleSection>
                      )}
                      {(report.tribunal_resolved?.length ?? 0) > 0 && (
                        <CollapsibleSection
                          icon={<Shield className="w-3.5 h-3.5" />}
                          title="Tribunal Resolved"
                          count={report.tribunal_resolved?.length}
                          color="violet"
                        >
                          <div className="pt-4 divide-y divide-white/[0.04]">
                            {report.tribunal_resolved.map((f, i) => (
                              <div key={i} className="py-3">
                                <p className="text-[11px] text-foreground/55 font-mono leading-relaxed">
                                  {String(
                                    (f as Record<string, unknown>).resolution ??
                                      (f as Record<string, unknown>)
                                        .plain_description ??
                                      "Dispute resolved by tribunal consensus.",
                                  )}
                                </p>
                              </div>
                            ))}
                          </div>
                        </CollapsibleSection>
                      )}
                    </>
                  )}
                </div>
              )}

              {/* ══════════════════════════════════════════════════════════ */}
              {/* 8. DEEP VS INITIAL COMPARISON                           */}
              {/* ══════════════════════════════════════════════════════════ */}
              {isDeepPhase && (
                <div className="space-y-3">
                  <SectionHeader
                    icon={<Layers className="w-3.5 h-3.5 text-violet-400" />}
                    label="Phase Comparison"
                    sub="Initial vs Deep Analysis delta"
                  />
                  <ComparisonPanel
                    report={report}
                    activeAgentIds={activeAgentIds}
                  />
                </div>
              )}

              {/* ══════════════════════════════════════════════════════════ */}
              {/* 9. UNCERTAINTY & LIMITATIONS                            */}
              {/* ══════════════════════════════════════════════════════════ */}
              {report.uncertainty_statement &&
                !isBoilerplateUncertainty(report.uncertainty_statement) && (
                  <CollapsibleSection
                    icon={<AlertCircle className="w-3.5 h-3.5" />}
                    title="Uncertainty & Limitations"
                    color="amber-muted"
                  >
                    <div className="pt-4">
                      <p className="text-[11px] text-foreground/45 font-mono leading-relaxed">
                        {report.uncertainty_statement}
                      </p>
                    </div>
                  </CollapsibleSection>
                )}

              {/* ══════════════════════════════════════════════════════════ */}
              {/* 10. CHAIN OF CUSTODY                                    */}
              {/* ══════════════════════════════════════════════════════════ */}
              <CollapsibleSection
                icon={<Lock className="w-3.5 h-3.5" />}
                title="Chain of Custody"
                color="amber-muted"
              >
                <div className="pt-4 space-y-4">
                  {report.report_hash && (
                    <div>
                      <div className="flex items-center gap-2 text-[8px] font-mono font-bold uppercase tracking-widest text-amber-400/50 mb-2">
                        <ShieldCheck className="w-3 h-3" /> Integrity Hash
                        [SHA-256]
                      </div>
                      <p
                        className="text-[9px] font-mono text-foreground/30 break-all leading-relaxed p-3 rounded-xl border"
                        style={{
                          background: "rgba(255,255,255,0.02)",
                          borderColor: "rgba(255,255,255,0.06)",
                        }}
                      >
                        {report.report_hash}
                      </p>
                    </div>
                  )}
                  {report.cryptographic_signature && (
                    <div>
                      <div className="flex items-center gap-2 text-[8px] font-mono font-bold uppercase tracking-widest text-amber-400/50 mb-2">
                        <Fingerprint className="w-3 h-3" /> Cryptographic
                        Signature [ECDSA P-256]
                      </div>
                      <p
                        className="text-[9px] font-mono text-foreground/30 break-all leading-relaxed p-3 rounded-xl border"
                        style={{
                          background: "rgba(255,255,255,0.02)",
                          borderColor: "rgba(255,255,255,0.06)",
                        }}
                      >
                        {report.cryptographic_signature}
                      </p>
                    </div>
                  )}
                  <div className="flex items-center gap-2 text-[8px] font-mono font-bold text-foreground/20 uppercase tracking-tight">
                    <Shield className="w-3 h-3" /> Signature verified by arbiter
                    consensus protocol.
                  </div>
                </div>
              </CollapsibleSection>

              {/* ══════════════════════════════════════════════════════════ */}
              {/* 11. INVESTIGATOR NOTES                                  */}
              {/* ══════════════════════════════════════════════════════════ */}
              <InvestigatorAnnotation reportId={report.report_id} />

              {/* ══════════════════════════════════════════════════════════ */}
              {/* NAVIGATION BUTTONS                                      */}
              {/* ══════════════════════════════════════════════════════════ */}
              <div className="pt-6 border-t border-white/[0.05]">
                <div className="flex flex-col sm:flex-row gap-3 justify-center">
                  <button
                    onClick={handleNew}
                    className="flex items-center gap-2.5 px-8 py-4 rounded-full text-xs font-black uppercase tracking-[0.2em] text-emerald-400 border border-emerald-500/20 bg-emerald-500/[0.06] hover:bg-emerald-500/[0.12] hover:border-emerald-500/30 transition-all cursor-pointer shadow-[0_0_20px_rgba(52,211,153,0.08)]"
                  >
                    <RotateCcw className="w-4 h-4" />
                    New Analysis
                    <ArrowRight className="w-3.5 h-3.5 opacity-50" />
                  </button>
                  <button
                    onClick={handleHome}
                    className="flex items-center gap-2.5 px-8 py-4 rounded-full text-xs font-black uppercase tracking-[0.2em] text-foreground/50 border border-white/[0.07] bg-white/[0.03] hover:bg-white/[0.06] hover:border-white/[0.12] transition-all cursor-pointer"
                  >
                    <Home className="w-4 h-4" />
                    Back to Home
                    <ArrowRight className="w-3.5 h-3.5 opacity-50" />
                  </button>
                </div>
              </div>
            </div>
          )}
        </main>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TIMELINE ENTRY
// ═══════════════════════════════════════════════════════════════════════════════
function TimelineEntry({
  icon,
  accentBg,
  accentBorder,
  label,
  labelColor,
  timestamp,
  detail,
  duration,
  badge,
  confidence,
}: {
  icon: React.ReactNode;
  accentBg: string;
  accentBorder: string;
  label: string;
  labelColor: string;
  timestamp?: string;
  detail?: string;
  duration?: string | null;
  badge?: string;
  confidence?: number;
}) {
  return (
    <div className="flex items-start gap-4">
      <div
        className="w-10 h-10 rounded-full shrink-0 flex items-center justify-center z-10"
        style={{ background: accentBg, border: `1px solid ${accentBorder}` }}
      >
        {icon}
      </div>
      <div className="flex-1 pt-2 pb-1">
        <div className="flex items-center gap-2 flex-wrap">
          <p className={clsx("text-[10px] font-bold", labelColor)}>{label}</p>
          {timestamp && (
            <span className="text-[8px] font-mono text-foreground/25">
              {timestamp}
            </span>
          )}
          {duration && (
            <span
              className="text-[8px] font-mono px-1.5 py-0.5 rounded text-foreground/35"
              style={{
                background: "rgba(255,255,255,0.05)",
                border: "1px solid rgba(255,255,255,0.07)",
              }}
            >
              +{duration}
            </span>
          )}
        </div>
        {detail && (
          <p className="text-[9px] font-mono text-foreground/30 mt-0.5">
            {detail}
          </p>
        )}
        {confidence !== undefined && (
          <span
            className={clsx(
              "text-[8px] font-mono font-bold mt-0.5 inline-block",
              confColor(confidence),
            )}
          >
            {Math.round(confidence * 100)}% conf
          </span>
        )}
      </div>
      {badge && (
        <div
          className={clsx(
            "text-[8px] font-mono font-bold uppercase tracking-wider mt-2.5 px-2 py-0.5 rounded-full border shrink-0",
            badge === "complete"
              ? "text-emerald-400 border-emerald-500/20 bg-emerald-500/10"
              : badge === "signed"
                ? "text-amber-400 border-amber-500/20 bg-amber-500/10"
                : badge === "skipped"
                  ? "text-foreground/20 border-white/[0.08] bg-white/[0.02]"
                  : "text-amber-400 border-amber-500/20 bg-amber-500/10",
          )}
        >
          {badge}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// COMPARISON PANEL
// ═══════════════════════════════════════════════════════════════════════════════
function ComparisonPanel({
  report,
  activeAgentIds,
}: {
  report: ReportDTO;
  activeAgentIds: string[];
}) {
  const allFindings = Object.values(report.per_agent_findings ?? {}).flat();
  const initialFindings = allFindings.filter(
    (f) =>
      (((f.metadata as Record<string, unknown>)?.analysis_phase as string) ??
        "initial") === "initial",
  );
  const deepFindings = allFindings.filter(
    (f) => (f.metadata as Record<string, unknown>)?.analysis_phase === "deep",
  );

  const initialConf =
    initialFindings.length > 0
      ? initialFindings.reduce(
          (s, f) =>
            s +
            (f.raw_confidence_score ??
              f.calibrated_probability ??
              f.confidence_raw ??
              0),
          0,
        ) / initialFindings.length
      : 0;
  const deepConf =
    deepFindings.length > 0
      ? deepFindings.reduce(
          (s, f) =>
            s +
            (f.raw_confidence_score ??
              f.calibrated_probability ??
              f.confidence_raw ??
              0),
          0,
        ) / deepFindings.length
      : 0;

  const newFindings = deepFindings.filter((df) => {
    const dfTool =
      ((df.metadata as Record<string, unknown>)?.tool_name as string) ??
      df.finding_type;
    return !initialFindings.some((ifo) => {
      const ifoTool =
        ((ifo.metadata as Record<string, unknown>)?.tool_name as string) ??
        ifo.finding_type;
      return ifoTool === dfTool && ifo.finding_type === df.finding_type;
    });
  });

  return (
    <div className="space-y-3">
      <div
        className="rounded-2xl overflow-hidden"
        style={{
          background: "rgba(255,255,255,0.025)",
          border: "1px solid rgba(255,255,255,0.07)",
        }}
      >
        <div className="grid grid-cols-3 gap-0">
          <div
            className="text-center p-5 space-y-2"
            style={{ borderRight: "1px solid rgba(255,255,255,0.05)" }}
          >
            <p className="text-[8px] font-mono font-bold uppercase tracking-[0.2em] text-foreground/25">
              Initial
            </p>
            <p className="text-3xl font-black font-mono text-emerald-400">
              {Math.round(initialConf * 100)}%
            </p>
            <p className="text-[8px] font-mono text-foreground/20">
              {initialFindings.length} findings
            </p>
          </div>
          <div className="flex items-center justify-center gap-2 text-violet-400/40">
            <div className="w-6 h-px bg-violet-400/20" />
            <ArrowRight className="w-4 h-4" />
            <div className="w-6 h-px bg-violet-400/20" />
          </div>
          <div
            className="text-center p-5 space-y-2"
            style={{ borderLeft: "1px solid rgba(255,255,255,0.05)" }}
          >
            <p className="text-[8px] font-mono font-bold uppercase tracking-[0.2em] text-foreground/25">
              Deep
            </p>
            <p className="text-3xl font-black font-mono text-violet-400">
              {Math.round(deepConf * 100)}%
            </p>
            <p className="text-[8px] font-mono text-foreground/20">
              {deepFindings.length} findings
            </p>
          </div>
        </div>
        <div
          className="px-5 py-2.5 flex justify-center gap-4 text-[8px] font-mono text-foreground/25"
          style={{ borderTop: "1px solid rgba(255,255,255,0.04)" }}
        >
          <span>
            New findings:{" "}
            <span className="text-violet-400 font-bold">
              +{newFindings.length}
            </span>
          </span>
          <span className="text-white/10">|</span>
          <span>
            Combined:{" "}
            <span className="text-foreground/40 font-bold">
              {allFindings.length}
            </span>
          </span>
        </div>
      </div>

      {newFindings.length > 0 && (
        <div
          className="rounded-2xl overflow-hidden"
          style={{
            background: "rgba(139,92,246,0.04)",
            border: "1px solid rgba(139,92,246,0.15)",
          }}
        >
          <div
            className="px-5 py-3 flex items-center gap-2.5"
            style={{ borderBottom: "1px solid rgba(139,92,246,0.1)" }}
          >
            <Zap className="w-3.5 h-3.5 text-violet-400 shrink-0" />
            <p className="text-[10px] font-bold uppercase tracking-widest text-violet-400">
              New from Deep Analysis
            </p>
            <span className="text-[8px] font-mono text-violet-400/50 px-1.5 py-0.5 rounded-full bg-violet-500/10 border border-violet-500/20">
              +{newFindings.length}
            </span>
          </div>
          <div className="p-4 space-y-2">
            {newFindings.slice(0, 10).map((f, i) => (
              <div
                key={i}
                className="flex items-start gap-3 p-3 rounded-xl"
                style={{
                  background: "rgba(139,92,246,0.04)",
                  border: "1px solid rgba(139,92,246,0.1)",
                }}
              >
                <span className="w-5 h-5 rounded-md bg-violet-500/10 border border-violet-500/20 flex items-center justify-center text-[8px] font-black font-mono text-violet-400 shrink-0">
                  {i + 1}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-[9px] font-mono font-bold text-violet-400/60 uppercase tracking-wider mb-0.5">
                    {f.finding_type}
                  </p>
                  <p className="text-[10px] text-foreground/55 leading-relaxed">
                    {stripToolPrefix(
                      f.reasoning_summary || f.court_statement || "—",
                    )}
                  </p>
                </div>
                <span
                  className={clsx(
                    "text-[9px] font-mono font-bold shrink-0",
                    confColor(
                      f.raw_confidence_score ??
                        f.calibrated_probability ??
                        f.confidence_raw ??
                        0,
                    ),
                  )}
                >
                  {Math.round(
                    (f.raw_confidence_score ??
                      f.calibrated_probability ??
                      f.confidence_raw ??
                      0) * 100,
                  )}
                  %
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div
        className="rounded-2xl overflow-hidden"
        style={{
          background: "rgba(255,255,255,0.025)",
          border: "1px solid rgba(255,255,255,0.07)",
        }}
      >
        <div
          className="px-5 py-3 flex items-center gap-2.5"
          style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}
        >
          <Layers className="w-3.5 h-3.5 text-foreground/35" />
          <p className="text-[10px] font-bold uppercase tracking-widest text-foreground/50">
            Per-Agent Phase Breakdown
          </p>
        </div>
        <div className="divide-y divide-white/[0.04]">
          {activeAgentIds.map((agentId) => {
            const meta = AGENT_META[agentId];
            if (!meta) return null;
            const agentInit = initialFindings.filter(
              (f) => f.agent_id === agentId,
            );
            const agentDeep = deepFindings.filter(
              (f) => f.agent_id === agentId,
            );
            const iConf =
              agentInit.length > 0
                ? agentInit.reduce(
                    (s, f) =>
                      s +
                      (f.raw_confidence_score ??
                        f.calibrated_probability ??
                        f.confidence_raw ??
                        0),
                    0,
                  ) / agentInit.length
                : 0;
            const dConf =
              agentDeep.length > 0
                ? agentDeep.reduce(
                    (s, f) =>
                      s +
                      (f.raw_confidence_score ??
                        f.calibrated_probability ??
                        f.confidence_raw ??
                        0),
                    0,
                  ) / agentDeep.length
                : 0;
            const delta = dConf - iConf;
            return (
              <div
                key={agentId}
                className="flex items-center gap-4 px-5 py-3.5"
              >
                <div
                  className="w-2 h-2 rounded-full shrink-0"
                  style={{ background: meta.accentFill }}
                />
                <span
                  className={clsx(
                    "text-[10px] font-bold w-24 shrink-0",
                    meta.accentColor,
                  )}
                >
                  {meta.name}
                </span>
                <div className="flex-1 flex items-center gap-4 text-[9px] font-mono">
                  <span className="text-foreground/30">Init:</span>
                  <span className={clsx("font-bold", confColor(iConf))}>
                    {Math.round(iConf * 100)}%
                  </span>
                  <span className="text-foreground/15">→</span>
                  <span className="text-foreground/30">Deep:</span>
                  <span className={clsx("font-bold", confColor(dConf))}>
                    {Math.round(dConf * 100)}%
                  </span>
                  {agentDeep.length > 0 && (
                    <span
                      className={clsx(
                        "font-bold text-[8px]",
                        delta >= 0 ? "text-emerald-400" : "text-rose-400",
                      )}
                    >
                      {delta >= 0 ? "+" : ""}
                      {Math.round(delta * 100)}%
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// INVESTIGATOR ANNOTATION
// ═══════════════════════════════════════════════════════════════════════════════
function InvestigatorAnnotation({ reportId }: { reportId: string }) {
  const [note, setNote] = useState("");
  const [saved, setSaved] = useState(false);
  const storageKey = `fc_annotation_${reportId}`;

  useEffect(() => {
    try {
      const v = localStorage.getItem(storageKey);
      if (v) setNote(v);
    } catch {
      /* ignore */
    }
  }, [storageKey]);

  const handleSave = () => {
    try {
      localStorage.setItem(storageKey, note);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch {
      /* ignore */
    }
  };

  return (
    <div
      className="rounded-2xl p-5 space-y-3"
      style={{
        background: "rgba(255,255,255,0.025)",
        border: "1px solid rgba(255,255,255,0.07)",
      }}
    >
      <div className="flex items-center gap-2">
        <FileText className="w-3.5 h-3.5 text-foreground/30" />
        <p className="text-[9px] font-mono font-bold uppercase tracking-widest text-foreground/30">
          Investigator Notes
        </p>
      </div>
      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="Add post-analysis observations, recommendations, or annotations..."
        className="w-full h-24 bg-black/20 border border-white/[0.06] rounded-xl p-3 text-[11px] text-foreground/65 font-mono leading-relaxed resize-none placeholder:text-foreground/15 focus:outline-none focus:border-amber-500/30 transition-colors"
      />
      <div className="flex items-center justify-between">
        <p className="text-[8px] font-mono text-foreground/15">
          Saved locally — not included in signed report
        </p>
        <button
          onClick={handleSave}
          className="text-[9px] font-mono font-bold uppercase tracking-widest px-3 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 hover:bg-amber-500/20 transition-colors cursor-pointer"
        >
          {saved ? "Saved ✓" : "Save Note"}
        </button>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// HISTORY PANEL
// ═══════════════════════════════════════════════════════════════════════════════
function HistoryPanel({ onDismiss }: { onDismiss: () => void }) {
  const router = useRouter();
  const [history, setHistory] = useState<HistoryItem[]>([]);

  useEffect(() => {
    try {
      const s = localStorage.getItem("forensic_history");
      if (s) setHistory(JSON.parse(s));
    } catch {
      /* ignore */
    }
  }, []);

  const removeItem = (sessionId: string) => {
    const updated = history.filter((h) => h.sessionId !== sessionId);
    setHistory(updated);
    localStorage.setItem("forensic_history", JSON.stringify(updated));
  };

  const clearAll = () => {
    setHistory([]);
    localStorage.setItem("forensic_history", JSON.stringify([]));
  };

  if (history.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-4 text-center">
        <History className="w-10 h-10 text-foreground/15" />
        <p className="text-foreground/30 text-sm font-medium">
          No analysis history yet.
        </p>
        <button
          onClick={() => router.push("/evidence")}
          className="flex items-center gap-2 px-6 py-2.5 rounded-full text-[10px] font-bold uppercase tracking-wider text-foreground/50 border border-white/[0.07] bg-white/[0.03] hover:bg-white/[0.06] transition-all cursor-pointer"
        >
          Start New Investigation
        </button>
        <button
          onClick={onDismiss}
          className="text-[10px] font-bold uppercase tracking-widest text-foreground/30 hover:text-foreground/60 transition-colors mt-2"
        >
          Dismiss Panel
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-widest text-foreground/50">
            Analysis History
          </p>
          <p className="text-[9px] font-mono text-foreground/25 mt-0.5">
            {history.length} session{history.length !== 1 ? "s" : ""} stored
            locally
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={clearAll}
            className="flex items-center gap-1.5 text-[9px] font-mono font-bold uppercase tracking-widest text-foreground/20 hover:text-rose-400 transition-colors cursor-pointer px-3 py-1.5 rounded-lg hover:bg-rose-500/10 border border-transparent hover:border-rose-500/20"
          >
            <Trash2 className="w-3 h-3" /> Clear All
          </button>
          <button
            onClick={onDismiss}
            className="flex items-center gap-1.5 text-[9px] font-mono font-bold uppercase tracking-widest px-4 py-1.5 rounded-full border border-white/[0.07] bg-white/[0.03] hover:bg-white/[0.06] text-foreground/60 transition-colors cursor-pointer"
          >
            Dismiss
          </button>
        </div>
      </div>
      <div className="space-y-2">
        {history.map((item) => {
          const vc = getVerdictConfig(item.verdict);
          return (
            <div
              key={item.sessionId}
              className="group flex items-center justify-between gap-4 p-4 rounded-2xl border border-white/[0.06] transition-all hover:bg-white/[0.02]"
              style={{ background: "rgba(255,255,255,0.02)" }}
            >
              <div className="flex items-center gap-4 min-w-0">
                <div className="w-14 h-14 shrink-0 rounded-xl overflow-hidden glass-panel border border-white/[0.06] flex items-center justify-center relative bg-black/40">
                  <EvidenceThumbnail
                    mime={item.mime || null}
                    thumbnail={item.thumbnail || null}
                    size="sm"
                  />
                  <div
                    className={clsx(
                      "absolute bottom-0 left-0 right-0 h-1",
                      vc.color === "emerald"
                        ? "bg-emerald-500"
                        : vc.color === "red"
                          ? "bg-red-500"
                          : "bg-amber-500",
                    )}
                  />
                </div>
                <div className="min-w-0 space-y-1">
                  <p className="text-sm font-bold text-foreground/90 truncate">
                    {item.fileName}
                  </p>
                  <div className="flex items-center gap-3 flex-wrap">
                    <div className="flex items-center gap-1.5">
                      <vc.Icon className={clsx("w-3 h-3", vc.textColor)} />
                      <span
                        className={clsx(
                          "text-[10px] font-black uppercase tracking-wider",
                          vc.textColor,
                        )}
                      >
                        {vc.label}
                      </span>
                    </div>
                    <span className="w-1 h-1 rounded-full bg-white/20" />
                    <span className="text-[9px] font-mono text-foreground/40">
                      {fmtTimestamp(item.timestamp)}
                    </span>
                    <span className="w-1 h-1 rounded-full bg-white/20" />
                    <span
                      className={clsx(
                        "text-[8px] font-mono font-bold uppercase tracking-widest px-2 py-0.5 rounded border",
                        item.type === "Deep"
                          ? "text-violet-400 border-violet-500/20 bg-violet-500/10"
                          : "text-cyan-400 border-cyan-500/20 bg-cyan-500/10",
                      )}
                    >
                      {item.type} Phase
                    </span>
                  </div>
                </div>
              </div>
              <button
                onClick={() => removeItem(item.sessionId)}
                className="p-1.5 rounded-lg hover:bg-rose-500/10 text-foreground/15 hover:text-rose-400 transition-all opacity-0 group-hover:opacity-100 cursor-pointer border border-transparent hover:border-rose-500/20"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
