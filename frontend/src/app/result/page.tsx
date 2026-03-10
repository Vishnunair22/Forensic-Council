"use client";

import React, { useState, useEffect, useMemo, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileCheck, CheckCircle, Search, Lock, AlertTriangle, Trash2, Loader2, ChevronDown,
  MonitorPlay, Mic2, Image as ImageIcon, Binary, Home, RotateCcw
} from "lucide-react";
import { useRouter } from "next/navigation";
import clsx from "clsx";
import { useForensicData, mapReportDtoToReport } from "@/hooks/useForensicData";
import { useSound } from "@/hooks/useSound";
import { getReport, type ReportDTO } from "@/lib/api";

// Agent configuration with colors and icons
const AGENT_CONFIG: Record<string, { name: string; role: string; icon: React.ReactNode; color: string; borderColor: string; bgColor: string }> = {
  "Agent1": {
    name: "Image Forensics",
    role: "Visual Analysis & Authenticity",
    icon: <ImageIcon className="w-6 h-6" />,
    color: "emerald",
    borderColor: "border-emerald-500/30",
    bgColor: "bg-emerald-500/10"
  },
  "Agent2": {
    name: "Audio Forensics",
    role: "Sound & Voice Analysis",
    icon: <Mic2 className="w-6 h-6" />,
    color: "cyan",
    borderColor: "border-cyan-500/30",
    bgColor: "bg-cyan-500/10"
  },
  "Agent3": {
    name: "Object Detection",
    role: "Content Recognition",
    icon: <Search className="w-6 h-6" />,
    color: "indigo",
    borderColor: "border-indigo-500/30",
    bgColor: "bg-indigo-500/10"
  },
  "Agent4": {
    name: "Video Forensics",
    role: "Temporal & Motion Analysis",
    icon: <MonitorPlay className="w-6 h-6" />,
    color: "pink",
    borderColor: "border-pink-500/30",
    bgColor: "bg-pink-500/10"
  },
  "Agent5": {
    name: "Metadata Analysis",
    role: "Digital Footprints",
    icon: <Binary className="w-6 h-6" />,
    color: "amber",
    borderColor: "border-amber-500/30",
    bgColor: "bg-amber-500/10"
  }
};

const COLOR_STYLES: Record<string, { text: string; textBright: string; badge: string; ring: string }> = {
  emerald: { text: "text-emerald-400", textBright: "text-emerald-300", badge: "bg-emerald-500/20 border-emerald-500/30", ring: "ring-emerald-500/30" },
  cyan: { text: "text-cyan-400", textBright: "text-cyan-300", badge: "bg-cyan-500/20 border-cyan-500/30", ring: "ring-cyan-500/30" },
  indigo: { text: "text-indigo-400", textBright: "text-indigo-300", badge: "bg-indigo-500/20 border-indigo-500/30", ring: "ring-indigo-500/30" },
  pink: { text: "text-pink-400", textBright: "text-pink-300", badge: "bg-pink-500/20 border-pink-500/30", ring: "ring-pink-500/30" },
  amber: { text: "text-amber-400", textBright: "text-amber-300", badge: "bg-amber-500/20 border-amber-500/30", ring: "ring-amber-500/30" },
};

export default function ResultPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<"result" | "history">("result");
  const [agentAnalysisOpen, setAgentAnalysisOpen] = useState(false);
  const [mounted, setMounted] = useState(false);

  const { history, currentReport, deleteFromHistory, clearHistory, addToHistory, isLoading } = useForensicData();
  const [realReport, setRealReport] = useState<ReportDTO | null>(null);
  const [isLoadingRealReport, setIsLoadingRealReport] = useState(false);
  const { playSound } = useSound();

  useEffect(() => {
    const sessionId = sessionStorage.getItem('forensic_session_id');
    if (!sessionId) return;

    let cancelled = false;
    let timerId: ReturnType<typeof setTimeout>;
    const MAX_ATTEMPTS = 30;
    let attempts = 0;

    setIsLoadingRealReport(true);

    const poll = async () => {
      if (cancelled) return;
      attempts++;
      try {
        const response = await getReport(sessionId);
        if (response.status === 'complete' && response.report) {
          if (!cancelled) {
            setRealReport(response.report);
            const mapped = mapReportDtoToReport(response.report);
            addToHistory(mapped);
            setIsLoadingRealReport(false);
          }
          return; // done — stop polling
        }
      } catch (err) {
        console.error("Failed to fetch report:", err);
      }
      // Still in-progress or error — retry unless we hit max
      if (!cancelled && attempts < MAX_ATTEMPTS) {
        timerId = setTimeout(poll, 4000);
      } else if (!cancelled) {
        setIsLoadingRealReport(false); // give up gracefully
      }
    };

    poll();

    return () => {
      cancelled = true;
      clearTimeout(timerId);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const playSoundRef = useRef(playSound);
  useEffect(() => {
    playSoundRef.current = playSound;
  }, [playSound]);

  useEffect(() => {
    setMounted(true);
    playSoundRef.current("success");
  }, []);

  const getFileName = () => {
    if (currentReport?.fileName) return currentReport.fileName;
    const sessionName = sessionStorage.getItem('forensic_file_name');
    if (sessionName) return sessionName;
    if (realReport?.case_id) return realReport.case_id;
    return "Analysis Result";
  };

  // Extract verdict based on confidence scores
  const verdict = useMemo(() => {
    const scores: number[] = [];
    if (realReport?.per_agent_findings) {
      Object.values(realReport.per_agent_findings).forEach((findings) => {
        findings.forEach((f) => {
          const c = f.calibrated_probability ?? f.confidence_raw ?? 0;
          if (c !== null) scores.push(c);
        });
      });
    }

    if (scores.length === 0) return null;
    const avg = scores.reduce((a, b) => a + b, 0) / scores.length;

    const contested = realReport?.contested_findings?.length ?? 0;
    if (avg >= 0.75 && contested === 0) return { label: "AUTHENTIC", color: "emerald", icon: CheckCircle };
    if (avg >= 0.5 || (contested > 0 && contested <= 2)) return { label: "REVIEW REQUIRED", color: "amber", icon: AlertTriangle };
    return { label: "MANIPULATION DETECTED", color: "red", icon: AlertTriangle };
  }, [realReport]);

  if (!mounted) return null;

  return (
    <div className="min-h-screen bg-[#050505] text-white p-6 pb-20 overflow-x-hidden">
      {/* Background */}
      <div className="fixed inset-0 -z-50">
        <div className="absolute inset-0 bg-[#030303]" />
        <div className="absolute top-0 left-1/4 w-[600px] h-[600px] bg-emerald-900/15 rounded-full blur-[120px]" />
        <div className="absolute bottom-0 right-1/4 w-[500px] h-[500px] bg-cyan-900/10 rounded-full blur-[100px]" />
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff03_1px,transparent_1px),linear-gradient(to_bottom,#ffffff03_1px,transparent_1px)] bg-[size:40px_40px]" />
      </div>

      {/* Header */}
      <header className="flex-shrink-0 w-full mb-10">
        <div className="max-w-6xl mx-auto flex items-center justify-between py-5 px-2 border-b border-white/[0.06]">
          <div
            className="flex items-center space-x-3 cursor-pointer group"
            onClick={() => { playSound("click"); router.push('/'); }}
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
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-50" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
            </span>
            Analysis Complete
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto">
        {/* Tabs */}
        <div className="flex space-x-6 mb-8 border-b border-white/10">
          <button
            onClick={() => setActiveTab("result")}
            className={clsx(
              "pb-3 text-lg font-medium transition-all relative outline-none",
              activeTab === "result" ? "text-emerald-400" : "text-slate-500 hover:text-slate-300"
            )}
          >
            Current Analysis
            {activeTab === "result" && (
              <motion.div layoutId="tab" className="absolute bottom-0 left-0 w-full h-0.5 bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.5)]" />
            )}
          </button>
          <button
            onClick={() => setActiveTab("history")}
            className={clsx(
              "pb-3 text-lg font-medium transition-all relative outline-none",
              activeTab === "history" ? "text-emerald-400" : "text-slate-500 hover:text-slate-300"
            )}
          >
            History
            {activeTab === "history" && (
              <motion.div layoutId="tab" className="absolute bottom-0 left-0 w-full h-0.5 bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.5)]" />
            )}
          </button>
        </div>

        <AnimatePresence mode="wait">
          {activeTab === "result" ? (
            <motion.div key="result" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="flex flex-col gap-8">
              {isLoading || isLoadingRealReport ? (
                <div className="p-12 text-center text-slate-500 bg-white/5 rounded-3xl border border-white/5 flex flex-col items-center">
                  <Loader2 className="w-10 h-10 animate-spin mb-4 text-emerald-500" />
                  <p className="font-mono text-lg tracking-widest uppercase">Synthesizing final report...</p>
                </div>
              ) : realReport || currentReport ? (
                <>
                  {/* Verdict Banner */}
                  {verdict && (
                    <motion.div
                      initial={{ opacity: 0, scale: 0.97 }}
                      animate={{ opacity: 1, scale: 1 }}
                      className={`relative overflow-hidden rounded-2xl border p-8 flex items-center justify-between gap-6 shadow-xl
                        ${verdict.color === "emerald" ? "bg-emerald-950/30 border-emerald-500/40" :
                          verdict.color === "amber" ? "bg-amber-950/30 border-amber-500/40" :
                            "bg-red-950/30 border-red-500/40"}`}
                    >
                      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/25 to-transparent" />
                      <div className="relative z-10 flex items-center gap-6">
                        <div className={clsx(
                          "p-4 rounded-xl",
                          verdict.color === "emerald" ? "bg-emerald-500/20" : verdict.color === "amber" ? "bg-amber-500/20" : "bg-red-500/20"
                        )}>
                          <verdict.icon className={clsx(
                            "w-8 h-8",
                            verdict.color === "emerald" ? "text-emerald-400" : verdict.color === "amber" ? "text-amber-400" : "text-red-400"
                          )} />
                        </div>
                        <div>
                          <h2 className={clsx(
                            "text-3xl font-black",
                            verdict.color === "emerald" ? "text-emerald-400" : verdict.color === "amber" ? "text-amber-400" : "text-red-400"
                          )}>
                            {verdict.label}
                          </h2>
                          <p className="text-slate-400 text-sm mt-1">Evidence Assessment Complete</p>
                        </div>
                      </div>
                    </motion.div>
                  )}

                  {/* File Info */}
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

                  {/* Executive Summary */}
                  <div className="bg-white/[0.02] border border-white/10 rounded-2xl p-6">
                    <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
                      <FileCheck className="w-5 h-5 text-emerald-400" />
                      Executive Summary
                    </h3>
                    <p className="text-slate-300 leading-relaxed">
                      {realReport?.executive_summary || "Analysis complete. Review findings below."}
                    </p>
                  </div>

                  {/* Key Findings */}
                  {realReport?.cross_modal_confirmed && realReport.cross_modal_confirmed.length > 0 && (
                    <div className="bg-white/[0.02] border border-white/10 rounded-2xl p-6">
                      <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
                        <CheckCircle className="w-5 h-5 text-emerald-400" />
                        Key Findings (Cross-Modal Confirmed)
                      </h3>
                      <div className="space-y-3">
                        {realReport.cross_modal_confirmed.map((finding, idx) => (
                          <div key={idx} className="flex items-start gap-3 p-4 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
                            <CheckCircle className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" />
                            <div className="flex-1">
                              <p className="font-medium text-white">{finding.finding_type}</p>
                              <p className="text-slate-400 text-sm mt-1">{finding.reasoning_summary}</p>
                              <p className="text-emerald-400 text-xs mt-2">
                                Confidence: {Math.round((finding.calibrated_probability ?? finding.confidence_raw ?? 0) * 100)}%
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* See Agent Analysis Button */}
                  <motion.button
                    onClick={() => setAgentAnalysisOpen(!agentAnalysisOpen)}
                    className="w-full flex items-center justify-between p-4 rounded-2xl bg-white/[0.04] border border-white/10 hover:bg-white/[0.08] hover:border-white/20 transition-all"
                  >
                    <div className="flex items-center gap-3">
                      <Search className="w-5 h-5 text-cyan-400" />
                      <span className="font-semibold text-white">See Detailed Agent Analysis</span>
                    </div>
                    <motion.div
                      animate={{ rotate: agentAnalysisOpen ? 180 : 0 }}
                      transition={{ duration: 0.3 }}
                    >
                      <ChevronDown className="w-5 h-5 text-slate-400" />
                    </motion.div>
                  </motion.button>

                  {/* Collapsible Agent Analysis Grid */}
                  <AnimatePresence>
                    {agentAnalysisOpen && (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: "auto" }}
                        exit={{ opacity: 0, height: 0 }}
                        transition={{ duration: 0.3 }}
                        className="overflow-hidden"
                      >
                        <div className="bg-white/[0.02] border border-white/10 rounded-2xl p-8">
                          <h3 className="text-2xl font-bold text-white mb-8">Agent Findings</h3>

                          {/* Dynamic Grid - Only show agents with findings */}
                          {(() => {
                            // Get all agents and filter to only those with findings
                            const allAgentIds = ["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"];
                            const activeAgents = allAgentIds.filter(agentId => {
                              const findings = realReport?.per_agent_findings?.[agentId] || [];
                              return findings.length > 0;
                            });
                            
                            if (activeAgents.length === 0) {
                              return (
                                <div className="text-center py-8">
                                  <p className="text-slate-400">No agents produced findings for this file type.</p>
                                </div>
                              );
                            }
                            
                            return (
                              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                {activeAgents.map((agentId, idx) => {
                                  const config = AGENT_CONFIG[agentId];
                                  const agentFindings = realReport?.per_agent_findings?.[agentId] || [];
                                  const colors = COLOR_STYLES[config.color];
                                  
                                  // Count initial vs deep findings
                                  const initialCount = agentFindings.filter(f => f.metadata?.analysis_phase !== 'deep').length;
                                  const deepCount = agentFindings.filter(f => f.metadata?.analysis_phase === 'deep').length;

                                  return (
                                    <motion.div
                                      key={agentId}
                                      initial={{ opacity: 0, y: 20 }}
                                      animate={{ opacity: 1, y: 0 }}
                                      transition={{ delay: idx * 0.1 }}
                                      className={`rounded-xl border p-6 bg-white/[0.02] ${config.borderColor} hover:bg-white/[0.04] transition-all`}
                                    >
                                      <div className="flex items-center gap-3 mb-4">
                                        <div className={`p-3 rounded-lg ${config.bgColor}`}>
                                          <div className={colors.text}>{config.icon}</div>
                                        </div>
                                        <div>
                                          <h4 className="font-bold text-white text-lg">{config.name}</h4>
                                          <p className="text-slate-400 text-xs">{config.role}</p>
                                        </div>
                                      </div>
                                      
                                      {/* Show finding counts */}
                                      <div className="flex gap-2 mb-3 text-xs">
                                        {initialCount > 0 && (
                                          <span className="px-2 py-1 rounded-full bg-slate-500/20 text-slate-300 border border-slate-500/30">
                                            {initialCount} Initial
                                          </span>
                                        )}
                                        {deepCount > 0 && (
                                          <span className="px-2 py-1 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30">
                                            {deepCount} Deep
                                          </span>
                                        )}
                                      </div>

                                      <div className="space-y-2 max-h-64 overflow-y-auto">
                                        {agentFindings.map((finding, fidx) => {
                                          const isDeep = finding.metadata?.analysis_phase === 'deep';
                                          return (
                                            <div key={fidx} className="text-sm">
                                              <div className="flex items-center gap-2 mb-1">
                                                <p className={`font-medium ${colors.text}`}>{finding.finding_type}</p>
                                                <span className={`text-[10px] px-2 py-0.5 rounded-full ${isDeep ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30' : 'bg-slate-500/20 text-slate-300 border border-slate-500/30'}`}>
                                                  {isDeep ? 'Deep' : 'Initial'}
                                                </span>
                                              </div>
                                              <p className="text-slate-400 text-xs mt-1">{finding.reasoning_summary}</p>
                                              <p className={`text-xs mt-2 ${colors.text}`}>
                                                Confidence: {Math.round((finding.calibrated_probability ?? finding.confidence_raw ?? 0) * 100)}%
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

                  {/* Uncertainty Statement */}
                  {realReport?.uncertainty_statement && (
                    <div className="bg-amber-950/20 border border-amber-500/30 rounded-2xl p-6">
                      <p className="text-amber-400 font-semibold text-sm mb-2 flex items-center gap-2">
                        <AlertTriangle className="w-4 h-4" />
                        Uncertainty Statement
                      </p>
                      <p className="text-slate-400 text-sm">{realReport.uncertainty_statement}</p>
                    </div>
                  )}

                  {/* Cryptographic Signature */}
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

                  {/* Action Buttons */}
                  <div className="flex gap-4 mt-12">
                    {/* New Analysis Button - takes to upload page */}
                    <motion.button
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                      onClick={() => {
                        playSound("click");
                        sessionStorage.removeItem('forensic_session_id');
                        sessionStorage.removeItem('forensic_file_name');
                        sessionStorage.removeItem('forensic_case_id');
                        router.push('/evidence');
                      }}
                      className="flex-1 flex items-center justify-center gap-3 px-6 py-4 rounded-xl
                        bg-white/[0.04] border border-white/[0.10] text-slate-300 font-semibold
                        hover:bg-white/[0.08] hover:border-white/20 hover:text-white
                        transition-all duration-200 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
                    >
                      <RotateCcw className="w-5 h-5" />
                      New Analysis
                    </motion.button>

                    {/* Back to Home Button - takes to landing page */}
                    <motion.button
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                      onClick={() => {
                        playSound("click");
                        router.push("/");
                      }}
                      className="flex-1 flex items-center justify-center gap-3 px-6 py-4 rounded-xl
                        bg-gradient-to-r from-emerald-500 to-cyan-500 text-white font-bold
                        hover:from-emerald-400 hover:to-cyan-400
                        hover:scale-[1.02] hover:shadow-[0_0_30px_rgba(16,185,129,0.4)]
                        transition-all duration-200
                        shadow-[0_4px_20px_rgba(16,185,129,0.3),inset_0_1px_0_rgba(255,255,255,0.2)]
                        border border-white/[0.15]"
                    >
                      <Home className="w-5 h-5" />
                      Back to Home
                    </motion.button>
                  </div>
                </>
              ) : (
                <div className="p-12 text-center text-slate-500 bg-white/5 rounded-3xl border border-white/5">
                  <p className="mb-8 max-w-sm mx-auto">You haven&apos;t initiated an investigation yet, or the data has expired from memory.</p>
                  <button
                    onClick={() => { playSound("click"); router.push('/'); }}
                    className="px-6 py-2 rounded-lg bg-emerald-500 text-white font-semibold hover:bg-emerald-400"
                  >
                    Back to Home
                  </button>
                </div>
              )}
            </motion.div>
          ) : (
            <motion.div key="history" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
              {history.length > 0 ? (
                <div className="space-y-4">
                  {history.map((report) => (
                    <div key={report.id} className="p-6 rounded-xl bg-white/[0.02] border border-white/10 flex items-center justify-between hover:bg-white/[0.04] transition-all cursor-pointer group">
                      <div className="flex-1">
                        <p className="font-semibold text-white">{report.fileName || "Analysis"}</p>
                        <p className="text-slate-500 text-sm mt-1">{report.timestamp}</p>
                      </div>
                      <button
                        onClick={(e) => handleDeleteOne(report.id, e)}
                        className="p-2 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                  <button
                    onClick={handleClearAll}
                    className="w-full py-2 mt-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 font-semibold hover:bg-red-500/20 transition-all"
                  >
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
    </div>
  );

  function handleDeleteOne(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    deleteFromHistory(id);
  }

  function handleClearAll() {
    clearHistory();
  }
}
