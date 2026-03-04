"use client";

import React, { useState, useEffect, useMemo, useRef, JSX } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { FileCheck, Activity, Shield, ArrowRight, CheckCircle, Clock, Search, ShieldAlert, ShieldCheck, ShieldX, ShieldAlert as ShieldAlertIcon, Cpu, Lock, Archive, Database, Eye, Hash, FileSymlink, AlertTriangle, Trash2, Loader2, ChevronDown, MonitorPlay, Mic2, Image as ImageIcon, Binary, GitMerge, GitPullRequest, Zap } from "lucide-react";
import { AGENTS_DATA } from "@/lib/constants";
import { useRouter } from "next/navigation";
import clsx from "clsx";
import { AgentIcon } from "@/components/ui/AgentIcon";
import { AgentResponseText } from "@/components/ui/AgentResponseText";
import { useForensicData } from "@/hooks/useForensicData";
import { useSound } from "@/hooks/useSound";
import { getReport, type ReportDTO, type AgentFindingDTO } from "@/lib/api";
import type { AgentResult, Report } from "@/types";

const VALID_AGENTS = new Set([...AGENTS_DATA.map(a => a.name), "Council Arbiter"]);

interface AgentAccumulator {
    [key: string]: AgentResult & { findings: string[] };
}

// Map exact agent_id to Domains for strict lookups
const DOMAIN_MAP: Record<string, { label: string, icon: React.ReactNode, color: string }> = {
    "Agent1": { label: "Image Analysis", icon: <ImageIcon className="w-5 h-5" />, color: "emerald" },
    "Agent2": { label: "Audio Analysis", icon: <Mic2 className="w-5 h-5" />, color: "cyan" },
    "Agent3": { label: "Object Detection", icon: <Search className="w-5 h-5" />, color: "indigo" },
    "Agent4": { label: "Video Analysis", icon: <MonitorPlay className="w-5 h-5" />, color: "pink" },
    "Agent5": { label: "Metadata Forensics", icon: <Binary className="w-5 h-5" />, color: "amber" }
};

const DOMAIN_STYLES: Record<string, { borderHover: string; text: string; bgLight: string; borderLight: string; bgSolid: string; }> = {
    slate: { borderHover: "hover:border-slate-500/30", text: "text-slate-400", bgLight: "bg-slate-500/10", borderLight: "border-slate-500/20", bgSolid: "bg-slate-500" },
    emerald: { borderHover: "hover:border-emerald-500/30", text: "text-emerald-400", bgLight: "bg-emerald-500/10", borderLight: "border-emerald-500/20", bgSolid: "bg-emerald-500" },
    cyan: { borderHover: "hover:border-cyan-500/30", text: "text-cyan-400", bgLight: "bg-cyan-500/10", borderLight: "border-cyan-500/20", bgSolid: "bg-cyan-500" },
    indigo: { borderHover: "hover:border-indigo-500/30", text: "text-indigo-400", bgLight: "bg-indigo-500/10", borderLight: "border-indigo-500/20", bgSolid: "bg-indigo-500" },
    pink: { borderHover: "hover:border-pink-500/30", text: "text-pink-400", bgLight: "bg-pink-500/10", borderLight: "border-pink-500/20", bgSolid: "bg-pink-500" },
    amber: { borderHover: "hover:border-amber-500/30", text: "text-amber-400", bgLight: "bg-amber-500/10", borderLight: "border-amber-500/20", bgSolid: "bg-amber-500" },
    red: { borderHover: "hover:border-red-500/30", text: "text-red-400", bgLight: "bg-red-500/10", borderLight: "border-red-500/20", bgSolid: "bg-red-500" }
};

const VERDICT_STYLES: Record<string, { text400: string; text400_70: string; text300: string; }> = {
    emerald: { text400: "text-emerald-400", text400_70: "text-emerald-400/70", text300: "text-emerald-300" },
    amber: { text400: "text-amber-400", text400_70: "text-amber-400/70", text300: "text-amber-300" },
    red: { text400: "text-red-400", text400_70: "text-red-400/70", text300: "text-red-300" }
};

export default function ResultPage() {
    const router = useRouter();
    const [activeTab, setActiveTab] = useState<"result" | "history">("result");
    const [detailsExpanded, setDetailsExpanded] = useState(false);

    // Use Hook
    const { history, currentReport, deleteFromHistory, clearHistory, isLoading } = useForensicData();

    // Real report data from API
    const [realReport, setRealReport] = useState<ReportDTO | null>(null);
    const [isLoadingRealReport, setIsLoadingRealReport] = useState(false);
    const [mounted, setMounted] = useState(false);
    const { playSound } = useSound();

    // Fetch real report from API
    useEffect(() => {
        const fetchRealReport = async () => {
            const sessionId = sessionStorage.getItem('forensic_session_id');

            if (sessionId) {
                setIsLoadingRealReport(true);
                try {
                    const response = await getReport(sessionId);
                    if (response.status === 'complete' && response.report) {
                        setRealReport(response.report);
                    }
                } catch (err) {
                    console.error("Failed to fetch report:", err);
                } finally {
                    setIsLoadingRealReport(false);
                }
            }
        };

        fetchRealReport();
    }, []);

    const playSoundRef = useRef(playSound);
    useEffect(() => {
        playSoundRef.current = playSound;
    }, [playSound]);

    // Prevent hydration mismatch
    useEffect(() => {
        setMounted(true);
        playSoundRef.current("success");
    }, []);

    const handleDeleteOne = (id: string, e: React.MouseEvent) => {
        e.stopPropagation();
        deleteFromHistory(id);
    };

    const handleClearAll = () => {
        clearHistory();
    };

    const formatDate = (isoString: string) => {
        return new Date(isoString).toLocaleString();
    };

    const getFileName = () => {
        if (currentReport?.fileName) return currentReport.fileName;
        const sessionName = sessionStorage.getItem('forensic_file_name');
        if (sessionName) return sessionName;
        if (realReport?.case_id) return realReport.case_id;
        return "Analysis Result";
    };

    // Synthesize domain results
    const domainData = useMemo(() => {
        const domains: Record<string, { label: string, icon: React.ReactNode, color: string, points: string[] }> = {};

        const ensureDomain = (idOrName: string) => {
            const config = DOMAIN_MAP[idOrName] || { label: idOrName, icon: <Search className="w-5 h-5" />, color: "slate" };
            if (!domains[config.label]) {
                domains[config.label] = { ...config, points: [] };
            }
            return config.label;
        };

        // Populate from real report first
        if (realReport?.per_agent_findings) {
            Object.entries(realReport.per_agent_findings).forEach(([agentId, findings]) => {
                const config = ensureDomain(agentId);
                findings.forEach(finding => {
                    domains[config].points.push(finding.reasoning_summary);
                });
            });
        } else if (currentReport?.agents) {
            currentReport.agents.forEach(agent => {
                if (VALID_AGENTS.has(agent.name)) {
                    const l = ensureDomain(agent.name);
                    domains[l].points.push(agent.result);
                }
            });
        }

        // Deduplicate points per domain
        Object.keys(domains).forEach(key => {
            domains[key].points = Array.from(new Set(domains[key].points));
        });

        return Object.values(domains).filter(d => d.points.length > 0);
    }, [realReport, currentReport]);

    // --- Compute overall verdict from agent data ---
    const verdict = useMemo(() => {
        let scores: number[] = [];
        let hasIncomplete = false;

        if (realReport?.per_agent_findings) {
            (Object.values(realReport.per_agent_findings) as AgentFindingDTO[][]).forEach((findings: AgentFindingDTO[]) => {
                findings.forEach((f: AgentFindingDTO) => {
                    if (f.status === "INCOMPLETE") hasIncomplete = true;
                    // calibrated_probability is authoritative over confidence_raw
                    const c = f.calibrated_probability ?? f.confidence_raw ?? null;
                    if (c !== null) scores.push(c);
                });
            });
        } else if (currentReport?.agents) {
            scores = currentReport.agents.map(a => a.confidence);
        }

        if (scores.length === 0) return null;
        let avg = scores.reduce((a, b) => a + b, 0) / scores.length;

        // Exact verdict metrics
        const contested = realReport?.contested_findings?.length ?? 0;

        if (hasIncomplete) {
            // Drop trust logically
            avg = Math.max(0, avg - 0.15);
        }

        if (avg >= 0.75 && contested === 0) return { label: "AUTHENTIC", color: "emerald", icon: "check", score: avg };
        if (avg >= 0.5 || contested > 0 && contested <= 2) return { label: "REVIEW REQUIRED", color: "amber", icon: "warn", score: avg };
        return { label: "MANIPULATION DETECTED", color: "red", icon: "alert", score: avg };
    }, [realReport, currentReport]);

    // Extracted verdict styles for easier lookup
    const vStyles = verdict ? (VERDICT_STYLES[verdict.color] || VERDICT_STYLES.emerald) : null;

    const totalAgents = realReport ? Object.keys(realReport.per_agent_findings ?? {}).length : (currentReport?.agents?.length ?? 0);
    const crossModalCount = realReport?.cross_modal_confirmed?.length ?? 0;
    const contestedCount = realReport?.contested_findings?.length ?? 0;
    const incompleteCount = realReport?.incomplete_findings?.length ?? 0;
    // Finding count should be sum of contested + cross_modal, fallback to agent size
    const totalFindings = crossModalCount + contestedCount || (totalAgents || 5);

    if (!mounted) return null;

    return (
        <div className="min-h-screen bg-[#050505] text-white p-6 pb-20 overflow-x-hidden">
            {/* --- Background --- */}
            <div className="fixed inset-0 -z-50">
                <div className="absolute inset-0 bg-[#030303]" />
                <div className="absolute top-0 left-1/4 w-[600px] h-[600px] bg-emerald-900/15 rounded-full blur-[120px]" />
                <div className="absolute bottom-0 right-1/4 w-[500px] h-[500px] bg-cyan-900/10 rounded-full blur-[100px]" />
                <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff03_1px,transparent_1px),linear-gradient(to_bottom,#ffffff03_1px,transparent_1px)] bg-[size:40px_40px]" />
            </div>

            <header className="flex-shrink-0 w-full mb-10">
                <div className="max-w-5xl mx-auto flex items-center justify-between py-5 px-2 border-b border-white/[0.06]">
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

            <main className="max-w-5xl mx-auto">
                {/* --- Tabs --- */}
                <div className="flex space-x-6 mb-8 border-b border-white/10">
                    <button
                        onClick={() => setActiveTab("result")}
                        className={clsx(
                            "pb-3 text-lg font-medium transition-all relative outline-none focus-visible:ring-2 ring-emerald-500",
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
                            "pb-3 text-lg font-medium transition-all relative outline-none focus-visible:ring-2 ring-emerald-500",
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
                        <motion.div
                            key="result"
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -10 }}
                            className="flex flex-col gap-6"
                        >
                            {isLoading || isLoadingRealReport ? (
                                <div className="p-12 text-center text-slate-500 bg-white/5 rounded-3xl border border-white/5 flex flex-col items-center">
                                    <Loader2 className="w-10 h-10 animate-spin mb-4 text-emerald-500" />
                                    <p className="font-mono text-lg tracking-widest uppercase">Synthesizing final report...</p>
                                </div>
                            ) : realReport || currentReport ? (
                                <>
                                    {/* --- TIER 1: Verdict Banner --- */}
                                    {verdict && (
                                        <motion.div
                                            initial={{ opacity: 0, scale: 0.97 }}
                                            animate={{ opacity: 1, scale: 1 }}
                                            className={`relative overflow-hidden rounded-3xl border p-8 md:p-10 flex flex-col md:flex-row items-center justify-between gap-6 shadow-2xl
                                                ${verdict.color === "emerald" ? "bg-emerald-950/30 border-emerald-500/40 shadow-[0_0_60px_rgba(16,185,129,0.08)]" :
                                                    verdict.color === "amber" ? "bg-amber-950/30 border-amber-500/40 shadow-[0_0_60px_rgba(245,158,11,0.08)]" :
                                                        "bg-red-950/30 border-red-500/40 shadow-[0_0_60px_rgba(239,68,68,0.08)]"}`}
                                        >
                                            {/* Glass shine on verdict banner */}
                                            <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/25 to-transparent" />
                                            <div className="absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-white/[0.03] to-transparent pointer-events-none rounded-t-3xl" />
                                            <div className={`absolute inset-0 opacity-5 pointer-events-none
                                                ${verdict.color === "emerald" ? "bg-[radial-gradient(circle_at_30%_50%,#10b981,transparent)]" :
                                                    verdict.color === "amber" ? "bg-[radial-gradient(circle_at_30%_50%,#f59e0b,transparent)]" :
                                                        "bg-[radial-gradient(circle_at_30%_50%,#ef4444,transparent)]"}`} />

                                            {/* Left: icon + verdict label */}
                                            <div className="flex items-center gap-6 relative z-10">
                                                <div className={`w-20 h-20 rounded-2xl flex items-center justify-center border shrink-0
                                                    ${verdict.color === "emerald" ? "bg-emerald-500/10 border-emerald-500/30" :
                                                        verdict.color === "amber" ? "bg-amber-500/10 border-amber-500/30" :
                                                            "bg-red-500/10 border-red-500/30"}`}>
                                                    {verdict.icon === "check" && <ShieldCheck className={`w-10 h-10 ${vStyles?.text400}`} />}
                                                    {verdict.icon === "warn" && <ShieldAlertIcon className={`w-10 h-10 ${vStyles?.text400}`} />}
                                                    {verdict.icon === "alert" && <ShieldX className={`w-10 h-10 ${vStyles?.text400}`} />}
                                                </div>
                                                <div>
                                                    <p className={`text-xs font-mono uppercase tracking-[0.2em] mb-1 ${vStyles?.text400_70}`}>Council Verdict</p>
                                                    <h2 className={`text-3xl md:text-4xl font-black tracking-tight ${vStyles?.text300}`}>
                                                        {verdict.label}
                                                    </h2>
                                                    <p className="text-slate-400 text-sm mt-1 font-mono truncate max-w-xs">{getFileName()}</p>
                                                </div>
                                            </div>

                                            {/* Right: stat chips */}
                                            <div className="flex flex-wrap gap-3 relative z-10 justify-center md:justify-end">
                                                <div className="px-5 py-3 rounded-2xl bg-black/40 border border-white/10 text-center min-w-[80px]">
                                                    <p className="text-2xl font-black text-white">{Math.round(verdict.score * 100)}<span className="text-sm text-slate-400">%</span></p>
                                                    <p className="text-[10px] uppercase tracking-widest text-slate-500 font-mono mt-0.5">Avg Conf</p>
                                                </div>
                                                <div className="px-5 py-3 rounded-2xl bg-black/40 border border-white/10 text-center min-w-[80px]">
                                                    <p className="text-2xl font-black text-white">{totalAgents || 5}</p>
                                                    <p className="text-[10px] uppercase tracking-widest text-slate-500 font-mono mt-0.5">Agents</p>
                                                </div>
                                                <div className="px-5 py-3 rounded-2xl bg-black/40 border border-white/10 text-center min-w-[80px]">
                                                    <p className="text-2xl font-black text-emerald-400">{crossModalCount}</p>
                                                    <p className="text-[10px] uppercase tracking-widest text-slate-500 font-mono mt-0.5">Confirmed</p>
                                                </div>
                                                {contestedCount > 0 && (
                                                    <div className="px-5 py-3 rounded-2xl bg-amber-950/40 border border-amber-500/20 text-center min-w-[80px]">
                                                        <p className="text-2xl font-black text-amber-400">{contestedCount}</p>
                                                        <p className="text-[10px] uppercase tracking-widest text-amber-500/70 font-mono mt-0.5">Contested</p>
                                                    </div>
                                                )}
                                                {incompleteCount > 0 && (
                                                    <div className="px-5 py-3 rounded-2xl bg-slate-900 border border-white/20 text-center min-w-[80px]">
                                                        <p className="text-2xl font-black text-slate-400">{incompleteCount}</p>
                                                        <p className="text-[10px] uppercase tracking-widest text-slate-500 font-mono mt-0.5">Incomplete</p>
                                                    </div>
                                                )}
                                                <div className="px-5 py-3 rounded-2xl bg-black/40 border border-white/10 text-center min-w-[80px]">
                                                    <p className="text-2xl font-black text-white">{totalFindings}</p>
                                                    <p className="text-[10px] uppercase tracking-widest text-slate-500 font-mono mt-0.5">Findings</p>
                                                </div>
                                            </div>
                                        </motion.div>
                                    )}

                                    {/* File + timestamp sub-header */}
                                    <div className="flex items-center justify-between px-2">
                                        <p className="text-slate-500 font-mono text-xs">
                                            <Clock className="w-3.5 h-3.5 inline mr-1.5" />
                                            {realReport?.signed_utc ? formatDate(realReport.signed_utc) : currentReport?.timestamp ? formatDate(currentReport.timestamp) : "—"}
                                        </p>
                                        {realReport?.cryptographic_signature && (
                                            <span className="text-[10px] font-mono text-emerald-500/60 flex items-center gap-1">
                                                <ShieldCheck className="w-3 h-3" /> Cryptographically Signed
                                            </span>
                                        )}
                                    </div>

                                    {/* --- 2. Cohesive Executive Overview --- */}
                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                        {/* Main Summary */}
                                        <div className="md:col-span-2 p-8 rounded-3xl bg-gradient-to-b from-white/[0.04] to-black/80 border border-white/[0.08] backdrop-blur-xl flex flex-col relative overflow-hidden">
                                            <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/20 to-transparent rounded-t-3xl" />
                                            <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-3">
                                                <FileCheck className="w-6 h-6 text-emerald-400" /> Consensus Report
                                            </h3>
                                            <p className="text-lg text-slate-300 leading-relaxed font-normal mb-8 border-b border-white/10 pb-8">
                                                {realReport?.executive_summary || currentReport?.summary || 'Analysis complete. No major anomalies detected.'}
                                            </p>

                                            {/* Domain Breakdown */}
                                            <h4 className="text-sm font-bold text-slate-400 mb-5 uppercase tracking-widest font-mono">Domain Findings</h4>
                                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                                {domainData.length > 0 ? domainData.map((domain, i) => {
                                                    const dStyle = DOMAIN_STYLES[domain.color] || DOMAIN_STYLES.slate;
                                                    return (
                                                        <div key={i} className={`flex flex-col gap-4 p-5 rounded-2xl bg-black/40 border border-white/5 ${dStyle.borderHover} transition-colors shadow-inner`}>
                                                            <div className={`flex items-center gap-3 shrink-0 ${dStyle.text} border-b border-white/5 pb-3`}>
                                                                <div className={`p-2 rounded-xl ${dStyle.bgLight} border ${dStyle.borderLight}`}>
                                                                    {domain.icon}
                                                                </div>
                                                                <span className="font-bold text-sm tracking-wide">{domain.label}</span>
                                                            </div>
                                                            <div className="flex-1 space-y-3 pt-1">
                                                                {domain.points.map((pt, j) => (
                                                                    <div key={j} className="flex gap-3 items-start">
                                                                        <div className={`w-1.5 h-1.5 rounded-full ${dStyle.bgSolid} mt-2 shrink-0 shadow-[0_0_8px_currentColor]`} />
                                                                        <p className="text-sm text-slate-300 leading-relaxed">
                                                                            {pt}
                                                                        </p>
                                                                    </div>
                                                                ))}
                                                            </div>
                                                        </div>
                                                    )
                                                }) : (
                                                    <p className="text-slate-500 italic text-sm">No specific domain details available.</p>
                                                )}
                                            </div>
                                        </div>

                                        {/* Cryptography Sidebar */}
                                        <div className="md:col-span-1 flex flex-col gap-6">
                                            {realReport ? (
                                                <div className="flex flex-col gap-4">
                                                    <div className="p-6 rounded-3xl bg-slate-900 border border-white/10 hover:border-emerald-500/20 transition-colors">
                                                        <h3 className="text-sm font-bold text-slate-300 mb-6 flex items-center gap-2 uppercase tracking-wide font-mono">
                                                            <Hash className="w-4 h-4 text-emerald-400" /> Signature Chain
                                                        </h3>
                                                        <div className="space-y-5">
                                                            <div>
                                                                <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-2 font-bold flex justify-between">
                                                                    <span>Report SHA-256</span>
                                                                </p>
                                                                <div className="bg-black/60 p-3 rounded-xl border border-white/5 relative group cursor-pointer overflow-hidden">
                                                                    <p className="text-xs font-mono text-emerald-400/80 break-all leading-relaxed group-hover:text-emerald-400 transition-colors">
                                                                        {realReport.report_hash || 'N/A'}
                                                                    </p>
                                                                </div>
                                                            </div>
                                                            <div>
                                                                <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-2 font-bold flex justify-between">
                                                                    <span>ECDSA Signature</span>
                                                                </p>
                                                                <div className="bg-black/60 p-3 rounded-xl border border-white/5 relative group cursor-pointer overflow-hidden">
                                                                    <p className="text-xs font-mono text-emerald-400/80 break-all leading-relaxed group-hover:text-emerald-400 transition-colors opacity-70">
                                                                        {realReport.cryptographic_signature ? `${realReport.cryptographic_signature.substring(0, 96)}...` : 'N/A'}
                                                                    </p>
                                                                </div>
                                                            </div>
                                                        </div>
                                                    </div>

                                                    {realReport.uncertainty_statement && (
                                                        <div className="p-6 rounded-3xl bg-amber-950/30 border border-amber-500/20">
                                                            <h3 className="text-sm font-bold text-amber-500 mb-3 flex items-center gap-2 uppercase tracking-wide font-mono">
                                                                <AlertTriangle className="w-4 h-4" /> Degree of Uncertainty
                                                            </h3>
                                                            <p className="text-sm text-amber-200/80 leading-relaxed">
                                                                {realReport.uncertainty_statement}
                                                            </p>
                                                        </div>
                                                    )}
                                                </div>
                                            ) : (
                                                <div className="flex-1 p-6 rounded-3xl bg-slate-900 border border-white/10 flex flex-col items-center justify-center text-center">
                                                    <Lock className="w-10 h-10 text-slate-700 mb-4" />
                                                    <p className="text-sm font-mono text-slate-500 uppercase tracking-widest leading-loose">Cryptography<br />Unavailable</p>
                                                </div>
                                            )}
                                        </div>
                                    </div>

                                    {/* --- TIER 4: Cross-Modal Confirmations --- */}
                                    {realReport?.cross_modal_confirmed && realReport.cross_modal_confirmed.length > 0 && (
                                        <div className="rounded-3xl bg-emerald-950/20 border border-emerald-500/20 overflow-hidden">
                                            <div className="px-6 py-5 border-b border-emerald-500/10 flex items-center gap-3">
                                                <div className="p-2 bg-emerald-500/10 rounded-xl">
                                                    <GitMerge className="w-5 h-5 text-emerald-400" />
                                                </div>
                                                <div>
                                                    <h3 className="font-bold text-white">Cross-Modal Confirmed Findings</h3>
                                                    <p className="text-xs text-emerald-400/60 font-mono mt-0.5 uppercase tracking-widest">Corroborated by multiple independent agents — highest trust</p>
                                                </div>
                                                <span className="ml-auto text-xs font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-3 py-1 rounded-full">
                                                    {realReport.cross_modal_confirmed.length} findings
                                                </span>
                                            </div>
                                            <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-5">
                                                {realReport.cross_modal_confirmed.map((f: any, i: number) => (
                                                    <div key={i} className="flex gap-4 p-5 rounded-2xl bg-black/40 border border-emerald-500/10 hover:border-emerald-500/40 hover:bg-emerald-950/20 transition-all shadow-inner group">
                                                        <div className="mt-1 shrink-0">
                                                            <div className="w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.9)] mt-1.5 group-hover:scale-125 transition-transform" />
                                                        </div>
                                                        <div className="flex-1 min-w-0">
                                                            <AgentResponseText text={f.reasoning_summary} className="text-sm text-slate-100 font-medium leading-relaxed" />
                                                            <p className="text-[10px] font-mono text-emerald-500/80 mt-3 uppercase tracking-widest bg-emerald-500/5 inline-block px-2 py-1 rounded-md border border-emerald-500/10">
                                                                {f.agent_name} · {f.finding_type}
                                                            </p>
                                                        </div>
                                                        <div className="shrink-0 text-right">
                                                            <span className="text-xs font-mono text-emerald-400 font-black bg-emerald-500/10 px-2 py-1 rounded-md border border-emerald-500/20">
                                                                {Math.round((f.calibrated_probability ?? f.confidence_raw ?? 0) * 100)}%
                                                            </span>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {/* --- TIER 5: Contested Findings --- */}
                                    {realReport?.contested_findings && realReport.contested_findings.length > 0 && (
                                        <div className="rounded-3xl bg-amber-950/20 border border-amber-500/20 overflow-hidden">
                                            <div className="px-6 py-5 border-b border-amber-500/10 flex items-center gap-3">
                                                <div className="p-2 bg-amber-500/10 rounded-xl">
                                                    <GitPullRequest className="w-5 h-5 text-amber-400" />
                                                </div>
                                                <div>
                                                    <h3 className="font-bold text-white">Contested Findings</h3>
                                                    <p className="text-xs text-amber-400/60 font-mono mt-0.5 uppercase tracking-widest">Agents reached conflicting conclusions — requires human review</p>
                                                </div>
                                                <span className="ml-auto text-xs font-mono bg-amber-500/10 text-amber-400 border border-amber-500/20 px-3 py-1 rounded-full">
                                                    {realReport.contested_findings.length} disputes
                                                </span>
                                            </div>
                                            <div className="p-6 space-y-4">
                                                {realReport.contested_findings.map((cf: any, i: number) => (
                                                    <div key={i} className="p-4 rounded-2xl bg-black/30 border border-amber-500/10">
                                                        <div className="flex items-center gap-2 mb-3">
                                                            <span className="text-[10px] font-mono bg-amber-500/10 text-amber-400 px-2 py-0.5 rounded-full uppercase tracking-widest">{cf.verdict}</span>
                                                        </div>
                                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                                            <div className="p-4 rounded-xl bg-black/50 border border-white/5 shadow-inner flex flex-col h-full">
                                                                <p className="text-[10px] font-mono text-slate-500 mb-2 uppercase tracking-widest bg-white/5 inline-table px-2 py-1 rounded self-start">{cf.finding_a?.agent_name}</p>
                                                                <AgentResponseText text={cf.finding_a?.reasoning_summary} className="text-sm text-slate-200 mt-1" />
                                                            </div>
                                                            <div className="p-4 rounded-xl bg-black/50 border border-white/5 shadow-inner flex flex-col h-full">
                                                                <p className="text-[10px] font-mono text-slate-500 mb-2 uppercase tracking-widest bg-white/5 inline-table px-2 py-1 rounded self-start">{cf.finding_b?.agent_name}</p>
                                                                <AgentResponseText text={cf.finding_b?.reasoning_summary} className="text-sm text-slate-200 mt-1" />
                                                            </div>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {/* --- TIER 6: Incomplete / Unsupported Findings --- */}
                                    {realReport?.incomplete_findings && realReport.incomplete_findings.length > 0 && (
                                        <div className="rounded-3xl bg-slate-900/40 border border-white/10 overflow-hidden mt-6">
                                            <button
                                                onClick={() => setDetailsExpanded(!detailsExpanded)}
                                                className="w-full px-6 py-5 border-b border-white/5 flex items-center gap-3 hover:bg-white/5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-500"
                                                aria-expanded={detailsExpanded}
                                            >
                                                <div className="p-2 bg-slate-800 rounded-xl">
                                                    <ShieldAlertIcon className="w-5 h-5 text-slate-400" />
                                                </div>
                                                <div className="text-left">
                                                    <h3 className="font-bold text-white">Incomplete Analysis</h3>
                                                    <p className="text-xs text-slate-500 font-mono mt-0.5 uppercase tracking-widest">Unsupported formats or missing sub-routines</p>
                                                </div>
                                                <span className="ml-auto text-xs font-mono bg-slate-800 text-slate-400 border border-white/5 px-3 py-1 rounded-full mr-3">
                                                    {realReport.incomplete_findings.length} findings
                                                </span>
                                                <ChevronDown className={`w-5 h-5 text-slate-500 transition-transform duration-300 ${detailsExpanded ? 'rotate-180' : ''}`} />
                                            </button>

                                            <AnimatePresence>
                                                {detailsExpanded && (
                                                    <motion.div
                                                        initial={{ height: 0, opacity: 0 }}
                                                        animate={{ height: "auto", opacity: 1 }}
                                                        exit={{ height: 0, opacity: 0 }}
                                                    >
                                                        <div className="p-6 space-y-4 bg-black/20">
                                                            {realReport.incomplete_findings.map((inc: any, i: number) => (
                                                                <div key={i} className="flex gap-4 p-5 rounded-2xl bg-black/40 border border-white/5 shadow-inner">
                                                                    <div className="mt-1 shrink-0">
                                                                        <div className="w-2.5 h-2.5 rounded-full bg-slate-600 mt-1.5" />
                                                                    </div>
                                                                    <div className="flex-1 min-w-0">
                                                                        <AgentResponseText text={inc.reasoning_summary} className="text-sm text-slate-400 font-medium leading-relaxed" />
                                                                        <p className="text-[10px] font-mono text-slate-500 mt-3 uppercase tracking-widest bg-white/5 inline-block px-2 py-1 rounded-md border border-white/10">
                                                                            {inc.agent_name} · {inc.finding_type}
                                                                        </p>
                                                                    </div>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </motion.div>
                                                )}
                                            </AnimatePresence>
                                        </div>
                                    )}

                                    {/* --- TIER 3: Primary Agent Findings Grid --- */}
                                    <div className="mt-6 mb-8">
                                        <h3 className="text-xl font-bold text-white mb-6 flex items-center gap-3">
                                            <Database className="w-6 h-6 text-emerald-400" /> Primary Agent Findings
                                        </h3>
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                            {(() => {
                                                const validCards: JSX.Element[] = [];

                                                if (realReport?.per_agent_findings) {
                                                    Object.entries(realReport.per_agent_findings).forEach(([agentId, findings]) => {
                                                        findings.forEach((f: any, idx: number) => {
                                                            if (!VALID_AGENTS.has(f.agent_name || "")) return;

                                                            const isComplete = f.status !== "INCOMPLETE";
                                                            const conf = f.calibrated_probability ?? f.confidence_raw ?? 0;
                                                            const confColor = conf >= 0.7 ? "text-emerald-400" : conf >= 0.4 ? "text-amber-400" : "text-red-400";
                                                            const agentStyle = DOMAIN_STYLES[DOMAIN_MAP[agentId]?.color || "slate"];

                                                            validCards.push(
                                                                <div key={`${agentId}-${idx}`} className={`flex flex-col h-full rounded-3xl p-6 border transition-all ${isComplete ? "bg-slate-900/60 border-white/10 hover:border-emerald-500/30 shadow-[0_4px_20px_rgba(0,0,0,0.5)]" : "bg-slate-900/30 border-white/5 opacity-70 grayscale-[0.8]"}`}>
                                                                    <div className="flex items-start justify-between mb-5 pb-5 border-b border-white/5">
                                                                        <div className="flex items-center gap-4">
                                                                            <div className={`w-12 h-12 rounded-2xl bg-black/60 border border-white/5 flex items-center justify-center shrink-0 shadow-inner ${isComplete ? 'group-hover:scale-105 transition-transform' : ''}`}>
                                                                                <AgentIcon role={f.finding_type || "analysis"} />
                                                                            </div>
                                                                            <div>
                                                                                <h4 className="font-bold text-slate-100 text-lg tracking-tight">{f.agent_name || agentId}</h4>
                                                                                <p className="text-[10px] text-slate-400 uppercase font-mono tracking-widest mt-1 opacity-80">{f.finding_type || "Analysis"}</p>
                                                                            </div>
                                                                        </div>

                                                                        <div className="text-right shrink-0">
                                                                            {isComplete ? (
                                                                                <>
                                                                                    <span className={`text-base font-mono font-black ${confColor}`}>
                                                                                        {Math.round(conf * 100)}%
                                                                                    </span>
                                                                                    <span className="text-[9px] text-slate-500 uppercase font-mono tracking-widest block mt-0.5">Confidence</span>
                                                                                </>
                                                                            ) : (
                                                                                <span className="text-xs font-mono font-bold bg-slate-800 text-slate-400 px-3 py-1 rounded-full border border-white/10 uppercase tracking-widest">
                                                                                    Incomplete
                                                                                </span>
                                                                            )}
                                                                        </div>
                                                                    </div>

                                                                    <div className="flex-1 w-full min-w-0">
                                                                        <AgentResponseText text={f.reasoning_summary || "No specific details provided."} className="text-sm text-slate-300 leading-relaxed font-normal w-full" />
                                                                    </div>

                                                                    {f.robustness_caveat && (
                                                                        <div className="mt-4 p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl">
                                                                            <p className="text-[10px] font-bold text-amber-500 uppercase tracking-widest mb-1 flex items-center gap-1">
                                                                                <AlertTriangle className="w-3 h-3" /> Robustness Caveat
                                                                            </p>
                                                                            <p className="text-xs text-amber-200/80 leading-snug">{f.robustness_caveat_detail || "Results may be subject to adversarial evasion."}</p>
                                                                        </div>
                                                                    )}

                                                                    {f.court_statement && (
                                                                        <div className="mt-4 p-4 bg-slate-950/60 border border-slate-700/50 rounded-xl relative overflow-hidden">
                                                                            <div className="absolute top-0 left-0 w-1 h-full bg-slate-500/50" />
                                                                            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2 flex items-center gap-1.5 ml-1">
                                                                                <Shield className="w-3 h-3" /> External Court Statement
                                                                            </p>
                                                                            <p className="text-sm text-slate-300 italic font-medium leading-relaxed ml-1">{f.court_statement}</p>
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            );
                                                        });
                                                    });
                                                } else if (currentReport?.agents) {
                                                    // Fallback for pre-DTO sessions
                                                    currentReport.agents.forEach((agent: any, i: number) => {
                                                        validCards.push(
                                                            <div key={`legacy-${i}`} className="flex flex-col h-full rounded-3xl p-6 border bg-slate-900/60 border-white/10 shadow-[0_4px_20px_rgba(0,0,0,0.5)]">
                                                                <div className="flex items-start justify-between mb-5 pb-5 border-b border-white/5">
                                                                    <div className="flex items-center gap-4">
                                                                        <div className="w-12 h-12 rounded-2xl bg-black/60 border border-white/5 flex items-center justify-center shrink-0">
                                                                            <AgentIcon role={agent.role} />
                                                                        </div>
                                                                        <div>
                                                                            <h4 className="font-bold text-slate-100 text-lg">{agent.name}</h4>
                                                                            <p className="text-[10px] text-slate-400 uppercase font-mono">{agent.role}</p>
                                                                        </div>
                                                                    </div>
                                                                    <div className="text-right shrink-0">
                                                                        <span className="text-base font-mono font-black text-emerald-400">{Math.round((agent.confidence || 0) * 100)}%</span>
                                                                    </div>
                                                                </div>
                                                                <AgentResponseText text={agent.result || ""} className="text-sm text-slate-300 leading-relaxed font-normal w-full" />
                                                            </div>
                                                        );
                                                    });
                                                }
                                                return validCards.length > 0 ? validCards : <p className="text-slate-500 italic px-4">No agent findings available.</p>;
                                            })()}
                                        </div>
                                    </div>

                                    {/* Action Buttons */}
                                    <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-10 pb-6">
                                        <button
                                            onClick={() => { playSound("click"); router.push('/evidence'); }}
                                            className="flex items-center gap-2.5 px-7 py-3.5 rounded-xl
                                                bg-gradient-to-r from-emerald-500 to-cyan-500 text-white font-bold text-sm
                                                hover:from-emerald-400 hover:to-cyan-400 hover:scale-[1.02]
                                                transition-all duration-200
                                                shadow-[0_4px_20px_rgba(16,185,129,0.25),inset_0_1px_0_rgba(255,255,255,0.2)]
                                                border border-white/[0.15]"
                                        >
                                            <Zap className="w-4 h-4" />
                                            Analyse Another File
                                        </button>
                                        <button
                                            onClick={() => { playSound("click"); router.push('/'); }}
                                            className="flex items-center gap-2.5 px-7 py-3.5 rounded-xl
                                                bg-white/[0.03] border border-white/[0.10] text-slate-300 font-semibold text-sm
                                                hover:bg-white/[0.07] hover:border-white/20 hover:text-white
                                                transition-all duration-200
                                                shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
                                        >
                                            ← Back to Home
                                        </button>
                                    </div>
                                </>
                            ) : (
                                <div className="text-center py-24 text-slate-500">
                                    <Archive className="w-16 h-16 mx-auto mb-6 opacity-40" />
                                    <h2 className="text-2xl font-bold text-white mb-2">No active analysis</h2>
                                    <p className="mb-8 max-w-sm mx-auto">You haven't initiated an investigation yet, or the data has expired from memory.</p>
                                    <button
                                        onClick={() => router.push('/evidence')}
                                        className="px-8 py-3 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 rounded-full hover:bg-emerald-500/20 transition-colors font-bold tracking-wide"
                                    >
                                        Begin Investigation
                                    </button>
                                </div>
                            )}
                        </motion.div>
                    ) : (
                        /* --- History Tab Content --- */
                        <motion.div
                            key="history"
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -10 }}
                        >
                            <div className="flex justify-between items-center mb-8 border-b border-white/5 pb-6">
                                <h3 className="text-xl font-bold text-white flex items-center gap-3">
                                    <Archive className="w-5 h-5 text-emerald-400" />
                                    Archived Sessions
                                </h3>
                                {history.length > 0 && (
                                    <button onClick={handleClearAll} className="text-red-400 hover:text-red-300 text-sm font-bold flex items-center transition-colors px-4 py-2 hover:bg-red-500/10 rounded-lg">
                                        <Trash2 className="w-4 h-4 mr-2" /> Format Archive
                                    </button>
                                )}
                            </div>

                            <div className="space-y-4">
                                <AnimatePresence>
                                    {history.length > 0 ? history.map((item: Report) => (
                                        <motion.div
                                            key={item.id}
                                            layout
                                            initial={{ opacity: 0, scale: 0.98 }}
                                            animate={{ opacity: 1, scale: 1 }}
                                            exit={{ opacity: 0, height: 0, marginBottom: 0, overflow: "hidden" }}
                                            className="p-6 rounded-2xl bg-slate-900 border border-white/10 hover:border-emerald-500/30 transition-colors flex flex-col md:flex-row items-start md:items-center justify-between group gap-4"
                                        >
                                            <div className="flex items-center gap-5">
                                                <div className="w-12 h-12 rounded-xl bg-slate-800 border border-white/5 shadow-inner flex items-center justify-center text-emerald-400 font-mono font-bold shrink-0">
                                                    FC
                                                </div>
                                                <div>
                                                    <h4 className="font-bold text-white text-lg">{item.fileName}</h4>
                                                    <div className="flex items-center text-sm text-slate-500 mt-1 font-mono">
                                                        <Clock className="w-4 h-4 mr-2" /> {formatDate(item.timestamp)}
                                                    </div>
                                                </div>
                                            </div>

                                            <div className="flex items-center gap-6 self-end md:self-auto md:ml-auto w-full md:w-auto justify-between md:justify-end border-t border-white/10 md:border-0 pt-4 md:pt-0 mt-2 md:mt-0">
                                                <div className="text-left md:text-right">
                                                    {(() => {
                                                        const avgConf = item.agents.length > 0
                                                            ? Math.round(item.agents.reduce((sum: number, a: { confidence: number }) => sum + a.confidence * 100, 0) / item.agents.length)
                                                            : 0;
                                                        const label = avgConf >= 80 ? "HIGH CONF" : avgConf >= 50 ? "MODERATE" : "LOW CONF";
                                                        const labelColor = avgConf >= 80 ? "text-emerald-400" : avgConf >= 50 ? "text-amber-400" : "text-red-400";
                                                        const bgCol = avgConf >= 80 ? "bg-emerald-500/10" : avgConf >= 50 ? "bg-amber-500/10" : "bg-red-500/10";

                                                        return (
                                                            <div className={`px-4 py-2 ${bgCol} rounded-lg border border-white/5 inline-flex flex-col`}>
                                                                <p className={`${labelColor} text-xs font-bold tracking-widest`}>{label}</p>
                                                                <p className="text-xs font-mono text-slate-400 mt-0.5">AV. {avgConf}%</p>
                                                            </div>
                                                        );
                                                    })()}
                                                </div>
                                                <button
                                                    onClick={(e) => handleDeleteOne(item.id, e)}
                                                    className="p-3 text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded-xl transition-all border border-transparent hover:border-red-500/20"
                                                    title="Permanently Delete Evidence Record"
                                                >
                                                    <Trash2 className="w-5 h-5" />
                                                </button>
                                            </div>
                                        </motion.div>
                                    )) : (
                                        <div className="text-center py-20 bg-slate-900/50 rounded-3xl border border-white/5 border-dashed">
                                            <Archive className="w-12 h-12 mx-auto text-slate-600 mb-4" />
                                            <p className="text-slate-400 font-medium">History archive is empty.</p>
                                        </div>
                                    )}
                                </AnimatePresence>
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>
            </main>
        </div>
    );
}
