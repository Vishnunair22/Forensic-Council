"use client";

/**
 * Result Page
 * ===========
 *
 * Shows the arbiter-compiled forensic report.
 *
 * Flow:
 *  - Polls backend for the compiled report (arbiter runs server-side after resume)
 *  - While waiting → shows "Arbiter deliberating..." animation
 *  - On arrival  → plays complete chime, renders structured report
 *
 * Bottom buttons (fixed):
 *   [ New Analysis ]   [ Back to Home ]
 *
 * On initial-analysis path there is also a "Deep Analysis" ghost button
 * beside "Back to Home" that re-opens the evidence page in deep mode.
 */

import React, { useState, useEffect, useMemo, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileCheck, CheckCircle, Search, Lock, AlertTriangle,
  Trash2, Loader2, ChevronDown, MonitorPlay, Mic2,
  Image as ImageIcon, Binary, Home, RotateCcw,
  ShieldCheck,
} from "lucide-react";
import { useRouter } from "next/navigation";
import clsx from "clsx";
import { useForensicData, mapReportDtoToReport } from "@/hooks/useForensicData";
import { useSound } from "@/hooks/useSound";
import { getReport, type ReportDTO } from "@/lib/api";

// ── Agent colours / icons ──────────────────────────────────────────────────

const AGENT_CONFIG: Record<string, {
  name: string; role: string;
  icon: React.ReactNode;
  color: string; borderColor: string; bgColor: string;
}> = {
  Agent1: { name: "Image Forensics",   role: "Visual Analysis & Authenticity",  icon: <ImageIcon className="w-6 h-6" />, color: "emerald", borderColor: "border-emerald-500/30", bgColor: "bg-emerald-500/10" },
  Agent2: { name: "Audio Forensics",   role: "Sound & Voice Analysis",           icon: <Mic2 className="w-6 h-6" />,      color: "cyan",    borderColor: "border-cyan-500/30",    bgColor: "bg-cyan-500/10"    },
  Agent3: { name: "Object Detection",  role: "Content Recognition",              icon: <Search className="w-6 h-6" />,    color: "indigo",  borderColor: "border-indigo-500/30",  bgColor: "bg-indigo-500/10"  },
  Agent4: { name: "Video Forensics",   role: "Temporal & Motion Analysis",       icon: <MonitorPlay className="w-6 h-6" />, color: "pink",   borderColor: "border-pink-500/30",    bgColor: "bg-pink-500/10"    },
  Agent5: { name: "Metadata Analysis", role: "Digital Footprints",               icon: <Binary className="w-6 h-6" />,    color: "amber",   borderColor: "border-amber-500/30",   bgColor: "bg-amber-500/10"   },
};

const COLOR_STYLES: Record<string, { text: string; textBright: string; badge: string }> = {
  emerald: { text: "text-emerald-400", textBright: "text-emerald-300", badge: "bg-emerald-500/20 border-emerald-500/30" },
  cyan:    { text: "text-cyan-400",    textBright: "text-cyan-300",    badge: "bg-cyan-500/20 border-cyan-500/30"       },
  indigo:  { text: "text-indigo-400",  textBright: "text-indigo-300",  badge: "bg-indigo-500/20 border-indigo-500/30"   },
  pink:    { text: "text-pink-400",    textBright: "text-pink-300",    badge: "bg-pink-500/20 border-pink-500/30"       },
  amber:   { text: "text-amber-400",   textBright: "text-amber-300",   badge: "bg-amber-500/20 border-amber-500/30"     },
};

// ── Arbiter compiling animation ───────────────────────────────────────────

function ArbiterCompiling() {
  const STEPS = [
    "Gathering agent findings...",
    "Resolving contested evidence...",
    "Running tribunal arbitration...",
    "Calibrating confidence scores...",
    "Generating executive summary...",
    "Signing cryptographic hash...",
    "Finalising court-ready report...",
  ];
  const [stepIdx, setStepIdx] = useState(0);

  useEffect(() => {
    const id = setInterval(() => {
      setStepIdx(prev => (prev + 1) % STEPS.length);
    }, 1400);
    return () => clearInterval(id);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex flex-col items-center justify-center min-h-[55vh] gap-8">
      {/* Pulsing arbiter ring */}
      <div className="relative w-28 h-28 flex items-center justify-center">
        <motion.div
          animate={{ scale: [1, 1.15, 1], opacity: [0.3, 0.6, 0.3] }}
          transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
          className="absolute inset-0 rounded-full bg-purple-500/20 border border-purple-500/30"
        />
        <motion.div
          animate={{ scale: [1, 1.08, 1], opacity: [0.5, 0.8, 0.5] }}
          transition={{ duration: 2, repeat: Infinity, ease: "easeInOut", delay: 0.3 }}
          className="absolute inset-3 rounded-full bg-purple-500/10 border border-purple-500/20"
        />
        <div className="relative z-10 w-14 h-14 rounded-full bg-purple-900/60 border border-purple-500/40 flex items-center justify-center shadow-[0_0_30px_rgba(168,85,247,0.3)]">
          <ShieldCheck className="w-7 h-7 text-purple-300" />
        </div>
        {/* Orbiting dot */}
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
          className="absolute inset-0"
        >
          <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1 w-2 h-2 rounded-full bg-purple-400 shadow-[0_0_8px_rgba(168,85,247,0.8)]" />
        </motion.div>
      </div>

      <div className="text-center">
        <h2 className="text-2xl font-bold text-white mb-2">Council Arbiter Deliberating</h2>
        <AnimatePresence mode="wait">
          <motion.p
            key={stepIdx}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.35 }}
            className="text-sm text-purple-300/80 font-mono"
          >
            {STEPS[stepIdx]}
          </motion.p>
        </AnimatePresence>
      </div>

      {/* Progress bar */}
      <div className="w-64 h-1 bg-white/5 rounded-full overflow-hidden">
        <motion.div
          animate={{ x: ["-100%", "200%"] }}
          transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut" }}
          className="h-full w-1/3 bg-gradient-to-r from-transparent via-purple-400 to-transparent"
        />
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────

export default function ResultPage() {
  const router = useRouter();
  const [agentAnalysisOpen, setAgentAnalysisOpen] = useState(false);
  const [mounted, setMounted] = useState(false);

  const { history, currentReport, deleteFromHistory, clearHistory, addToHistory, isLoading } = useForensicData();
  const [realReport, setRealReport] = useState<ReportDTO | null>(null);
  const [isLoadingRealReport, setIsLoadingRealReport] = useState(true);
  const [activeTab, setActiveTab] = useState<"result" | "history">("result");

  const { playSound } = useSound();
  const playSoundRef = useRef(playSound);
  useEffect(() => { playSoundRef.current = playSound; }, [playSound]);

  // Poll for arbiter report
  useEffect(() => {
    const sessionId = sessionStorage.getItem("forensic_session_id");
    if (!sessionId) { setIsLoadingRealReport(false); return; }

    let cancelled = false;
    let timerId: ReturnType<typeof setTimeout>;
    const MAX_ATTEMPTS = 40; // 40 × 4 s = ~2.7 min
    let attempts = 0;

    setIsLoadingRealReport(true);

    const poll = async () => {
      if (cancelled) return;
      attempts++;
      try {
        const response = await getReport(sessionId);
        if (response.status === "complete" && response.report) {
          if (!cancelled) {
            setRealReport(response.report);
            const mapped = mapReportDtoToReport(response.report);
            addToHistory(mapped);
            setIsLoadingRealReport(false);
            // Play result-ready chime
            setTimeout(() => playSoundRef.current("complete"), 100);
          }
          return;
        }
      } catch (err) {
        console.error("Failed to fetch report:", err);
      }
      if (!cancelled && attempts < MAX_ATTEMPTS) {
        timerId = setTimeout(poll, 4000);
      } else if (!cancelled) {
        setIsLoadingRealReport(false);
      }
    };

    poll();
    return () => { cancelled = true; clearTimeout(timerId); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setMounted(true);
  }, []);

  const getFileName = () => {
    if (currentReport?.fileName) return currentReport.fileName;
    const s = sessionStorage.getItem("forensic_file_name");
    if (s) return s;
    if (realReport?.case_id) return realReport.case_id;
    return "Analysis Result";
  };

  const verdict = useMemo(() => {
    const scores: number[] = [];
    if (realReport?.per_agent_findings) {
      Object.values(realReport.per_agent_findings).forEach(findings =>
        findings.forEach(f => {
          const c = f.calibrated_probability ?? f.confidence_raw ?? 0;
          if (c !== null) scores.push(c);
        })
      );
    }
    if (scores.length === 0) return null;
    const avg = scores.reduce((a, b) => a + b, 0) / scores.length;
    const contested = realReport?.contested_findings?.length ?? 0;
    if (avg >= 0.75 && contested === 0) return { label: "AUTHENTIC", color: "emerald", icon: CheckCircle };
    if (avg >= 0.5 || (contested > 0 && contested <= 2)) return { label: "REVIEW REQUIRED", color: "amber", icon: AlertTriangle };
    return { label: "MANIPULATION DETECTED", color: "red", icon: AlertTriangle };
  }, [realReport]);

  // Navigation helpers
  const handleBackToHome = () => {
    playSound("click");
    router.push("/");
  };

  const handleNewAnalysis = () => {
    playSound("click");
    sessionStorage.removeItem("forensic_session_id");
    sessionStorage.removeItem("forensic_file_name");
    sessionStorage.removeItem("forensic_case_id");
    router.push("/evidence");
  };

  if (!mounted) return null;

  const isLoaderVisible = isLoading || isLoadingRealReport;
  const hasReport = realReport || currentReport;

  return (
    <div className="min-h-screen bg-[#050505] text-white overflow-x-hidden">
      {/* Background */}
      <div className="fixed inset-0 -z-50">
        <div className="absolute inset-0 bg-[#030303]" />
        <div className="absolute top-0 left-1/4 w-[600px] h-[600px] bg-emerald-900/15 rounded-full blur-[120px]" />
        <div className="absolute bottom-0 right-1/4 w-[500px] h-[500px] bg-cyan-900/10 rounded-full blur-[100px]" />
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff03_1px,transparent_1px),linear-gradient(to_bottom,#ffffff03_1px,transparent_1px)] bg-[size:40px_40px]" />
      </div>

      {/* Header */}
      <header className="flex-shrink-0 w-full">
        <div className="max-w-6xl mx-auto flex items-center justify-between py-5 px-6 border-b border-white/[0.06]">
          <div
            className="flex items-center space-x-3 cursor-pointer group"
            onClick={handleBackToHome}
          >
            <div className="w-9 h-9 bg-gradient-to-br from-emerald-400/20 to-cyan-500/10 border border-emerald-500/30 rounded-lg flex items-center justify-center font-bold text-emerald-400 text-sm group-hover:border-emerald-400/50 transition-colors">
              FC
            </div>
            <span className="text-lg font-bold tracking-tight text-white/80 group-hover:text-white transition-colors">
              Forensic Council
            </span>
          </div>
          <div className="flex items-center gap-2 text-xs font-mono text-slate-600">
            <span className="relative flex h-2 w-2">
              <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-50 ${isLoaderVisible ? "bg-purple-400" : "bg-emerald-400"}`} />
              <span className={`relative inline-flex rounded-full h-2 w-2 ${isLoaderVisible ? "bg-purple-500" : "bg-emerald-500"}`} />
            </span>
            {isLoaderVisible ? "Arbiter compiling..." : "Report Ready"}
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 pb-40 pt-8">
        {/* Tabs */}
        <div className="flex space-x-6 mb-8 border-b border-white/10">
          {(["result", "history"] as const).map(tab => (
            <button key={tab} onClick={() => setActiveTab(tab)}
              className={clsx("pb-3 text-lg font-medium transition-all relative outline-none capitalize",
                activeTab === tab ? "text-emerald-400" : "text-slate-500 hover:text-slate-300")}>
              {tab === "result" ? "Current Analysis" : "History"}
              {activeTab === tab && (
                <motion.div layoutId="tab" className="absolute bottom-0 left-0 w-full h-0.5 bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.5)]" />
              )}
            </button>
          ))}
        </div>

        <AnimatePresence mode="wait">
          {activeTab === "result" ? (
            <motion.div key="result" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>

              {/* Arbiter compiling state */}
              {isLoaderVisible && <ArbiterCompiling />}

              {/* Report ready */}
              {!isLoaderVisible && hasReport && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.5 }}
                  className="flex flex-col gap-8"
                >
                  {/* Verdict banner */}
                  {verdict && (
                    <motion.div
                      initial={{ opacity: 0, scale: 0.96 }}
                      animate={{ opacity: 1, scale: 1 }}
                      transition={{ type: "spring", stiffness: 200, damping: 20 }}
                      className={`relative overflow-hidden rounded-2xl border p-8 flex items-center gap-6 shadow-xl
                        ${verdict.color === "emerald" ? "bg-emerald-950/30 border-emerald-500/40"
                          : verdict.color === "amber" ? "bg-amber-950/30 border-amber-500/40"
                          : "bg-red-950/30 border-red-500/40"}`}
                    >
                      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/25 to-transparent" />
                      {/* Glow sweep on mount */}
                      <motion.div
                        initial={{ x: "-100%", opacity: 0.5 }}
                        animate={{ x: "200%", opacity: 0 }}
                        transition={{ duration: 1.2, ease: "easeOut", delay: 0.2 }}
                        className="absolute inset-y-0 w-1/3 bg-gradient-to-r from-transparent via-white/8 to-transparent pointer-events-none"
                      />
                      <div className={clsx("p-4 rounded-xl shrink-0",
                        verdict.color === "emerald" ? "bg-emerald-500/20"
                        : verdict.color === "amber" ? "bg-amber-500/20" : "bg-red-500/20")}>
                        <verdict.icon className={clsx("w-8 h-8",
                          verdict.color === "emerald" ? "text-emerald-400"
                          : verdict.color === "amber" ? "text-amber-400" : "text-red-400")} />
                      </div>
                      <div>
                        <h2 className={clsx("text-3xl font-black",
                          verdict.color === "emerald" ? "text-emerald-400"
                          : verdict.color === "amber" ? "text-amber-400" : "text-red-400")}>
                          {verdict.label}
                        </h2>
                        <p className="text-slate-400 text-sm mt-1">Evidence Assessment Complete</p>
                      </div>
                    </motion.div>
                  )}

                  {/* File / case info */}
                  <div className="bg-white/[0.02] border border-white/10 rounded-2xl p-6">
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                      <div>
                        <p className="text-slate-500 text-sm uppercase tracking-widest font-mono">File Analyzed</p>
                        <p className="text-white font-semibold mt-2 truncate">{getFileName()}</p>
                      </div>
                      <div>
                        <p className="text-slate-500 text-sm uppercase tracking-widest font-mono">Case ID</p>
                        <p className="text-emerald-400 font-mono text-sm mt-2">{realReport?.case_id || "N/A"}</p>
                      </div>
                      <div>
                        <p className="text-slate-500 text-sm uppercase tracking-widest font-mono">Session ID</p>
                        <p className="text-cyan-400 font-mono text-xs mt-2 truncate">{realReport?.session_id || "N/A"}</p>
                      </div>
                    </div>
                  </div>

                  {/* Executive summary */}
                  <div className="bg-white/[0.02] border border-white/10 rounded-2xl p-6">
                    <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
                      <FileCheck className="w-5 h-5 text-emerald-400" />
                      Executive Summary
                    </h3>
                    <p className="text-slate-300 leading-relaxed">
                      {realReport?.executive_summary || currentReport?.summary || "Analysis complete. Review findings below."}
                    </p>
                  </div>

                  {/* Cross-modal confirmed findings */}
                  {realReport?.cross_modal_confirmed && realReport.cross_modal_confirmed.length > 0 && (
                    <div className="bg-white/[0.02] border border-white/10 rounded-2xl p-6">
                      <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
                        <CheckCircle className="w-5 h-5 text-emerald-400" />
                        Key Findings — Cross-Modal Confirmed
                      </h3>
                      <div className="space-y-3">
                        {realReport.cross_modal_confirmed.map((finding, idx) => (
                          <motion.div key={idx}
                            initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: idx * 0.07 }}
                            className="flex items-start gap-3 p-4 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
                            <CheckCircle className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
                            <div className="flex-1">
                              <p className="font-medium text-white">{finding.finding_type}</p>
                              <p className="text-slate-400 text-sm mt-1">{finding.reasoning_summary}</p>
                              <p className="text-emerald-400 text-xs mt-2">
                                Confidence: {Math.round((finding.calibrated_probability ?? finding.confidence_raw ?? 0) * 100)}%
                              </p>
                            </div>
                          </motion.div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Collapsible detailed agent analysis */}
                  <button
                    onClick={() => { playSound("click"); setAgentAnalysisOpen(v => !v); }}
                    className="w-full flex items-center justify-between p-4 rounded-2xl bg-white/[0.04] border border-white/10 hover:bg-white/[0.08] hover:border-white/20 transition-all"
                  >
                    <div className="flex items-center gap-3">
                      <Search className="w-5 h-5 text-cyan-400" />
                      <span className="font-semibold text-white">Detailed Agent Analysis</span>
                    </div>
                    <motion.div animate={{ rotate: agentAnalysisOpen ? 180 : 0 }} transition={{ duration: 0.3 }}>
                      <ChevronDown className="w-5 h-5 text-slate-400" />
                    </motion.div>
                  </button>

                  <AnimatePresence>
                    {agentAnalysisOpen && (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
                        exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.35 }}
                        className="overflow-hidden"
                      >
                        <div className="bg-white/[0.02] border border-white/10 rounded-2xl p-8">
                          <h3 className="text-2xl font-bold text-white mb-8">Per-Agent Findings</h3>
                          {(() => {
                            const activeAgents = ["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"].filter(id =>
                              (realReport?.per_agent_findings?.[id]?.length ?? 0) > 0
                            );
                            if (activeAgents.length === 0) return (
                              <p className="text-slate-400 text-center py-8">No agent findings available.</p>
                            );
                            return (
                              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                {activeAgents.map((agentId, idx) => {
                                  const cfg = AGENT_CONFIG[agentId];
                                  const allFindings = realReport?.per_agent_findings?.[agentId] || [];
                                  const colors = COLOR_STYLES[cfg.color];

                                  // Determine if the backend tagged findings with analysis_phase metadata
                                  const hasPhaseMetadata = allFindings.some(f => f.metadata?.analysis_phase);
                                  const deepFindings = allFindings.filter(f => f.metadata?.analysis_phase === "deep");
                                  const initialFindings = allFindings.filter(f => f.metadata?.analysis_phase !== "deep");

                                  // Without phase metadata: deduplicate by finding_type to avoid showing
                                  // the same finding from both initial + deep runs.
                                  let findings = allFindings;
                                  if (!hasPhaseMetadata) {
                                    const seen = new Map<string, typeof allFindings[0]>();
                                    allFindings.forEach(f => seen.set(f.finding_type, f));
                                    findings = Array.from(seen.values());
                                  }

                                  const initialCount = hasPhaseMetadata ? initialFindings.length : 0;
                                  const deepCount = hasPhaseMetadata ? deepFindings.length : 0;

                                  return (
                                    <motion.div key={agentId}
                                      initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
                                      transition={{ delay: idx * 0.08 }}
                                      className={`rounded-xl border p-6 bg-white/[0.02] ${cfg.borderColor} hover:bg-white/[0.04] transition-all`}>
                                      <div className="flex items-center gap-3 mb-4">
                                        <div className={`p-3 rounded-lg ${cfg.bgColor}`}>
                                          <div className={colors.text}>{cfg.icon}</div>
                                        </div>
                                        <div>
                                          <h4 className="font-bold text-white">{cfg.name}</h4>
                                          <p className="text-slate-400 text-xs">{cfg.role}</p>
                                        </div>
                                      </div>
                                      {/* Phase badges — only shown when backend sets phase metadata */}
                                      {hasPhaseMetadata && (
                                        <div className="flex gap-2 mb-3">
                                          {initialCount > 0 && (
                                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-500/20 text-slate-300 border border-slate-500/30">
                                              {initialCount} Initial
                                            </span>
                                          )}
                                          {deepCount > 0 && (
                                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30">
                                              {deepCount} Deep
                                            </span>
                                          )}
                                        </div>
                                      )}
                                      <div className="space-y-3 max-h-64 overflow-y-auto">
                                        {findings.map((f, fi) => {
                                          const isDeep = f.metadata?.analysis_phase === "deep";
                                          return (
                                            <div key={fi}>
                                              <div className="flex items-center gap-2 mb-0.5">
                                                <p className={`text-sm font-medium ${colors.text}`}>{f.finding_type}</p>
                                                {hasPhaseMetadata && (
                                                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${isDeep ? "bg-purple-500/20 text-purple-300 border border-purple-500/30" : "bg-slate-500/15 text-slate-400 border border-slate-600/20"}`}>
                                                    {isDeep ? "Deep" : "Initial"}
                                                  </span>
                                                )}
                                              </div>
                                              <p className="text-slate-400 text-xs">{f.reasoning_summary}</p>
                                              <p className={`text-xs mt-1 ${colors.text}`}>
                                                {Math.round((f.calibrated_probability ?? f.confidence_raw ?? 0) * 100)}% confidence
                                              </p>
                                            </div>
                                          );
                                        })}
                                      </div>
                                    </motion.div>
                                  );
                                })}
                              </div>
                            );
                          })()}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>

                  {/* Uncertainty statement */}
                  {realReport?.uncertainty_statement && (
                    <div className="bg-amber-950/20 border border-amber-500/30 rounded-2xl p-6">
                      <p className="text-amber-400 font-semibold text-sm mb-2 flex items-center gap-2">
                        <AlertTriangle className="w-4 h-4" />
                        Uncertainty Statement
                      </p>
                      <p className="text-slate-400 text-sm">{realReport.uncertainty_statement}</p>
                    </div>
                  )}

                  {/* Cryptographic signature */}
                  {realReport?.cryptographic_signature && (
                    <div className="bg-white/[0.02] border border-white/10 rounded-2xl p-6">
                      <p className="text-slate-400 text-sm font-mono mb-2 flex items-center gap-2">
                        <Lock className="w-4 h-4 text-cyan-400" />
                        Cryptographic Signature
                      </p>
                      <p className="text-slate-500 text-xs font-mono break-all">{realReport.cryptographic_signature}</p>
                      <p className="text-slate-600 text-xs mt-2">Signed: {realReport.signed_utc || "N/A"}</p>
                    </div>
                  )}
                </motion.div>
              )}

              {/* No report state */}
              {!isLoaderVisible && !hasReport && (
                <div className="p-12 text-center text-slate-500 bg-white/5 rounded-3xl border border-white/5">
                  <p className="mb-8 max-w-sm mx-auto">No investigation data found or it has expired from memory.</p>
                  <button onClick={handleBackToHome}
                    className="px-6 py-2 rounded-lg bg-emerald-500 text-white font-semibold hover:bg-emerald-400 transition-colors">
                    Back to Home
                  </button>
                </div>
              )}
            </motion.div>
          ) : (
            /* History tab */
            <motion.div key="history" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
              {history.length > 0 ? (
                <div className="space-y-4">
                  {history.map(report => (
                    <div key={report.id}
                      className="p-6 rounded-xl bg-white/[0.02] border border-white/10 flex items-center justify-between hover:bg-white/[0.04] transition-all cursor-pointer group">
                      <div className="flex-1">
                        <p className="font-semibold text-white">{report.fileName || "Analysis"}</p>
                        <p className="text-slate-500 text-sm mt-1">{report.timestamp}</p>
                      </div>
                      <button onClick={e => { e.stopPropagation(); deleteFromHistory(report.id); }}
                        className="p-2 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 opacity-0 group-hover:opacity-100 transition-opacity">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                  <button onClick={clearHistory}
                    className="w-full py-2 mt-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 font-semibold hover:bg-red-500/20 transition-all">
                    Clear History
                  </button>
                </div>
              ) : (
                <div className="p-12 text-center text-slate-500 bg-white/5 rounded-3xl border border-white/5">
                  <p>No history yet</p>
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      {/* ── Fixed bottom action bar ──────────────────────────────────────── */}
      <div className="fixed bottom-0 inset-x-0 z-50 pb-safe">
        <div className="max-w-6xl mx-auto px-6 pb-6">
          <div className="flex gap-3 p-3 rounded-2xl bg-black/80 backdrop-blur-xl border border-white/[0.08] shadow-[0_-8px_32px_rgba(0,0,0,0.6)]">

            {/* New Analysis — always left */}
            <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }}
              onClick={handleNewAnalysis}
              className="flex-1 flex items-center justify-center gap-2.5 px-5 py-3.5 rounded-xl
                bg-white/[0.05] border border-white/[0.10] text-slate-300 font-semibold text-sm
                hover:bg-white/[0.10] hover:border-white/20 hover:text-white
                transition-all duration-200 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
              <RotateCcw className="w-4 h-4" />
              New Analysis
            </motion.button>

          {/* Back to Home — always right */}
            <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }}
              onClick={handleBackToHome}
              className="flex-1 flex items-center justify-center gap-2.5 px-5 py-3.5 rounded-xl
                bg-gradient-to-r from-emerald-500 to-cyan-500 text-white font-bold text-sm
                hover:from-emerald-400 hover:to-cyan-400
                hover:shadow-[0_0_30px_rgba(16,185,129,0.4)]
                transition-all duration-200
                shadow-[0_4px_20px_rgba(16,185,129,0.25),inset_0_1px_0_rgba(255,255,255,0.2)]
                border border-white/[0.15]">
              <Home className="w-4 h-4" />
              Back to Home
            </motion.button>
          </div>
        </div>
      </div>
    </div>
  );
}
