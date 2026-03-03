"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
    Upload, FileWarning, Fingerprint, Search, Shield, Activity,
    Bot, Database, FileDigit, Scan, Zap, Crosshair, ChevronRight, CheckCircle2, AlertTriangle, AlertCircle, X, Check, Loader2
} from "lucide-react";
import clsx from "clsx";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
    DialogFooter
} from "@/components/ui/dialog";

import { AGENTS_DATA } from "@/lib/constants";
import { useForensicData } from "@/hooks/useForensicData";
import { useSimulation } from "@/hooks/useSimulation";
import { useSound } from "@/hooks/useSound";
import { startInvestigation, submitHITLDecision } from "@/lib/api";
import { AgentIcon } from "@/components/ui/AgentIcon";

export default function EvidencePage() {
    const router = useRouter();
    const { addToHistory, isLoading: isDataLoading } = useForensicData();
    const { playSound } = useSound();

    const [file, setFile] = useState<File | null>(null);
    const [isDragging, setIsDragging] = useState(false);
    const [validationError, setValidationError] = useState<string | null>(null);

    // Server states
    const [isUploading, setIsUploading] = useState(false);
    const [sessionId, setSessionId] = useState<string | null>(null);

    const {
        status,
        activeAgents,
        completedAgents,
        startSimulation,
        connectWebSocket,
        resetSimulation,
        hitlCheckpoint,
        errorMessage,
        dismissCheckpoint,
        totalAgents
    } = useSimulation({
        playSound,
        onComplete: () => {
            // Let the user digest the page before automatically moving or showing a button
        }
    });

    const fileInputRef = useRef<HTMLInputElement>(null);

    // Prompt user to pick file immediately if they haven't yet and haven't uploaded
    useEffect(() => {
        if (!file && status === "idle") {
            const tmr = setTimeout(() => {
                if (fileInputRef.current && status === "idle" && !file) {
                    fileInputRef.current.click();
                }
            }, 100);
            return () => clearTimeout(tmr);
        }
    }, [file, status]);

    // Validation
    const validateFile = (f: File): boolean => {
        setValidationError(null);
        if (f.size > 50 * 1024 * 1024) {
            setValidationError("File must be under 50MB");
            return false;
        }
        return true;
    };

    const handleFile = (f: File) => {
        if (validateFile(f)) {
            setFile(f);
            playSound("success");
            setTimeout(() => {
                triggerAnalysis(f);
            }, 500);
        } else {
            playSound("error");
        }
    };

    const triggerAnalysis = async (targetFile: File) => {
        if (!targetFile) return;
        setIsUploading(true);
        setValidationError(null);
        startSimulation(); // sets to 'initiating'

        try {
            const investigatorId = localStorage.getItem("investigatorId") || "REQ-" + Math.floor(Math.random() * 90000 + 10000);
            const caseId = "CASE-" + Date.now();
            const res = await startInvestigation(targetFile, caseId, investigatorId);

            setSessionId(res.session_id);
            sessionStorage.setItem('forensic_session_id', res.session_id);
            sessionStorage.setItem('forensic_file_name', targetFile.name);
            sessionStorage.setItem('forensic_case_id', caseId);
            sessionStorage.setItem('forensic_investigator_id', investigatorId);

            try {
                await connectWebSocket(res.session_id);
                setIsUploading(false);
            } catch (wsErr: any) {
                console.error("WS connect failed", wsErr);
                setValidationError("Failed to connect to simulation streams");

                // Also trigger the error overlay in development for backend errors
                if (process.env.NODE_ENV === 'development') {
                    window.dispatchEvent(new ErrorEvent('error', {
                        error: wsErr,
                        message: wsErr?.message || "Failed to connect to simulation streams"
                    }));
                }

                setIsUploading(false);
                resetSimulation();
            }

        } catch (err: any) {
            console.error(err);
            setValidationError(err.message || "Failed to start investigation");

            // Also trigger the error overlay in development for backend errors
            if (process.env.NODE_ENV === 'development') {
                window.dispatchEvent(new ErrorEvent('error', {
                    error: err,
                    message: err.message || "Failed to start investigation"
                }));
            }

            setIsUploading(false);
            resetSimulation();
            playSound("error");
        }
    };

    const handleHITLDecision = async (decision: 'APPROVE' | 'REDIRECT' | 'TERMINATE') => {
        if (!hitlCheckpoint) return;
        try {
            const { session_id, checkpoint_id, agent_id } = hitlCheckpoint;
            await submitHITLDecision({
                session_id,
                checkpoint_id,
                agent_id,
                decision: decision,
                note: `User chose: ${decision}`
            });
            dismissCheckpoint();
            playSound("success");
        } catch (err: any) {
            console.error("Failed to submit decision", err);

            // Also trigger the error overlay in development for backend errors
            if (process.env.NODE_ENV === 'development') {
                window.dispatchEvent(new ErrorEvent('error', {
                    error: err,
                    message: err?.message || "Failed to submit decision"
                }));
            }

            playSound("error");
        }
    };

    const handleAcceptAnalysis = () => {
        playSound("click");
        router.push("/result");
    };

    const validAgentsData = AGENTS_DATA.filter(a => a.name !== "Council Arbiter");

    return (
        <div className="min-h-screen bg-[#050505] text-white p-6 pb-20 overflow-x-hidden relative">
            <div className="fixed inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900/30 via-black to-black -z-50" />

            <header className="max-w-6xl mx-auto flex items-center justify-between mb-8 z-10 relative">
                <div
                    className="flex items-center space-x-3 cursor-pointer group"
                    onClick={() => {
                        if (status !== 'analyzing') router.push('/');
                    }}
                >
                    <div className="w-10 h-10 bg-emerald-500/10 border border-emerald-500/30 rounded-lg flex items-center justify-center font-bold text-emerald-400 group-hover:bg-emerald-500/20 transition-colors shadow-[0_0_15px_rgba(16,185,129,0.1)]">
                        FC
                    </div>
                    <span className="text-xl font-bold tracking-tight">Forensic Council</span>
                </div>
                {(status === "idle" || status === "error") && (
                    <button
                        onClick={() => fileInputRef.current?.click()}
                        className="text-emerald-400 font-mono text-sm hover:underline hover:text-emerald-300"
                    >
                        Browse System
                    </button>
                )}
            </header>

            <main className="max-w-6xl mx-auto relative z-10">
                <AnimatePresence mode="wait">
                    {(status === "idle" || status === "error") && !isUploading && (
                        <motion.div
                            key="upload"
                            initial={{ opacity: 0, scale: 0.98 }}
                            animate={{ opacity: 1, scale: 1 }}
                            exit={{ opacity: 0, y: -20 }}
                            className="flex flex-col items-center justify-center min-h-[60vh] max-w-2xl mx-auto"
                        >
                            <div className="text-center mb-10">
                                <h1 className="text-4xl md:text-5xl font-black mb-4 tracking-tight drop-shadow-lg">
                                    Initiate Investigation.
                                </h1>
                                <p className="text-slate-400 text-lg md:text-xl font-light">
                                    Upload cryptographic evidence to deploy the <span className="text-emerald-400 font-medium">Council Autonomous Parsing System</span>.
                                </p>
                            </div>

                            <div
                                onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                                onDragLeave={() => setIsDragging(false)}
                                onDrop={(e) => {
                                    e.preventDefault();
                                    setIsDragging(false);
                                    if (e.dataTransfer.files?.[0]) handleFile(e.dataTransfer.files[0]);
                                }}
                                onClick={() => fileInputRef.current?.click()}
                                className={clsx(
                                    "w-full p-12 md:p-16 rounded-[2rem] border-2 border-dashed flex flex-col items-center justify-center cursor-pointer transition-all duration-300 group shadow-2xl backdrop-blur-sm relative overflow-hidden",
                                    isDragging
                                        ? "border-emerald-400 bg-emerald-500/5"
                                        : "border-white/10 bg-slate-900/30 hover:border-emerald-500/50 hover:bg-slate-900/50"
                                )}
                            >
                                <input
                                    type="file"
                                    ref={fileInputRef}
                                    onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
                                    className="hidden"
                                    accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.txt"
                                />
                                <div className="absolute inset-0 bg-emerald-500/5 translate-y-full group-hover:translate-y-0 transition-transform duration-500 ease-out" />
                                <div className="w-20 h-20 md:w-24 md:h-24 rounded-full bg-black/50 border border-white/5 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-300 shadow-inner z-10">
                                    <Fingerprint className={clsx("w-10 h-10 md:w-12 md:h-12", isDragging ? "text-emerald-400" : "text-emerald-500/50")} />
                                </div>
                                <h3 className="text-2xl font-bold text-white mb-3 z-10">Target Evidence Fragment</h3>
                                <p className="text-slate-400 text-center font-mono text-xs uppercase tracking-widest z-10">
                                    Drag & drop or <span className="text-emerald-400 underline decoration-emerald-500/30 underline-offset-4">browse secure directory</span>
                                </p>
                                <div className="flex gap-4 mt-8 z-10">
                                    {['JPG/PNG', 'MP4/MOV', 'WAV/MP3'].map(ext => (
                                        <span key={ext} className="px-3 py-1 bg-white/5 border border-white/10 rounded-full text-[10px] font-mono text-slate-500 tracking-wider">
                                            {ext}
                                        </span>
                                    ))}
                                </div>
                            </div>

                            <AnimatePresence>
                                {(validationError || errorMessage || status === "error") && (
                                    <motion.div
                                        initial={{ opacity: 0, y: 10 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        exit={{ opacity: 0, y: -10 }}
                                        className="mt-6 flex items-center text-red-400 bg-red-500/10 px-5 py-3 rounded-xl border border-red-500/20 shadow-[0_0_15px_rgba(239,68,68,0.1)]"
                                    >
                                        <FileWarning className="w-5 h-5 mr-3" />
                                        <span className="font-medium text-sm">Target acquisition failed: {validationError || errorMessage}</span>
                                    </motion.div>
                                )}
                            </AnimatePresence>
                        </motion.div>
                    )}

                    {(status !== "idle" && status !== "error" || isUploading) && (
                        <motion.div
                            key="analysis"
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="w-full flex flex-col pt-4"
                        >
                            {/* Header Panel */}
                            <div className="bg-slate-900/40 border border-white/10 p-6 md:p-8 rounded-3xl backdrop-blur-xl mb-8 flex flex-col md:flex-row justify-between items-start md:items-center relative overflow-hidden shadow-2xl">
                                <div className="absolute top-0 right-0 w-96 h-96 bg-emerald-500/10 rounded-full blur-[100px] -mr-20 -mt-20 pointer-events-none" />
                                <div className="relative z-10">
                                    <p className="text-emerald-400 font-mono text-xs uppercase tracking-widest mb-3 flex items-center font-bold">
                                        <Activity className="w-4 h-4 mr-2" /> Live Operation
                                    </p>
                                    <h2 className="text-2xl md:text-3xl font-extrabold text-white tracking-tight break-all mb-1">
                                        {file?.name || "Target System Data"}
                                    </h2>
                                    <p className="text-sm font-mono text-slate-500 tracking-wider">
                                        Session ID: {sessionId || "Initializing..."}
                                    </p>
                                </div>

                                <div className="relative z-10 flex flex-col items-end gap-3 mt-6 md:mt-0 ml-auto bg-black/40 p-5 rounded-2xl border border-white/5 shadow-inner">
                                    <div className="flex items-center gap-3">
                                        <Shield className={clsx("w-5 h-5", status === "complete" ? "text-emerald-400" : "text-amber-400")} />
                                        <span className={clsx("font-bold text-sm tracking-widest uppercase font-mono", status === "complete" ? "text-emerald-400" : "text-amber-400")}>
                                            {status === "complete" ? "ANALYSIS COMPLETE" : "PROCESSING ACTIVE"}
                                        </span>
                                    </div>
                                    <div className="flex gap-2 text-xs font-mono">
                                        <span className="text-slate-500">AGENTS DEPLOYED:</span>
                                        <span className="text-slate-300 font-bold">{validAgentsData.length} UNITS</span>
                                    </div>
                                </div>
                            </div>

                            {/* Concurrent Agent Grid */}
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-10">
                                {validAgentsData.map((agent, i) => {
                                    const isComplete = completedAgents.find(a => a.id === agent.id);
                                    const isActive = activeAgents[agent.id];
                                    const isIdle = !isComplete && !isActive;

                                    return (
                                        <motion.div
                                            key={agent.id}
                                            initial={{ opacity: 0, y: 20 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            transition={{ delay: i * 0.05 }}
                                            className={clsx(
                                                "p-6 rounded-3xl border transition-all duration-500 ease-out flex flex-col h-full relative overflow-hidden backdrop-blur-md",
                                                isComplete
                                                    ? (isComplete.confidence >= 0.7
                                                        ? "bg-emerald-950/20 border-emerald-500/40 shadow-[0_0_30px_rgba(16,185,129,0.05)]"
                                                        : isComplete.confidence >= 0.4
                                                            ? "bg-amber-950/20 border-amber-500/30 shadow-[0_0_30px_rgba(245,158,11,0.05)]"
                                                            : "bg-red-950/20 border-red-500/30 shadow-[0_0_30px_rgba(239,68,68,0.05)]")
                                                    : isActive
                                                        ? "bg-slate-900 border-emerald-500/20 shadow-[0_0_20px_rgba(16,185,129,0.05)]"
                                                        : "bg-black/60 border-white/5 opacity-50 grayscale"
                                            )}
                                        >
                                            {isActive && (
                                                <div className="absolute top-0 right-0 p-4">
                                                    <Loader2 className="w-5 h-5 text-emerald-400 animate-spin" />
                                                </div>
                                            )}

                                            <div className="flex items-center gap-4 mb-4">
                                                <AgentIcon role={agent.role} active={!!isActive} />
                                                <div>
                                                    <h3 className="text-lg font-bold text-white tracking-tight">{agent.name}</h3>
                                                    <div className="text-[10px] font-mono tracking-widest text-slate-400 uppercase">
                                                        {agent.role}
                                                    </div>
                                                </div>
                                            </div>

                                            <div className="flex-1 rounded-xl bg-black/40 border border-white/5 p-4 relative overflow-hidden flex items-center mt-2 group">
                                                {isComplete ? (
                                                    <div className="text-sm text-emerald-100/90 leading-relaxed max-h-32 overflow-y-auto pr-2 custom-scrollbar">
                                                        <span className="text-emerald-500 mr-2 font-bold font-mono">▸</span>
                                                        {isComplete.result || "No specific anomalies reported."}
                                                    </div>
                                                ) : isActive ? (
                                                    <div className="w-full">
                                                        <div className="text-sm text-emerald-400 font-mono mb-2 flex items-center animate-pulse">
                                                            <Activity className="w-4 h-4 mr-2" /> Processing Data Stream...
                                                        </div>
                                                        <p className="text-xs text-slate-400 italic">"{isActive.thinking}"</p>
                                                    </div>
                                                ) : (
                                                    <div className="text-xs text-slate-600 font-mono tracking-widest uppercase flex flex-col items-center justify-center w-full h-full gap-2">
                                                        <Scan className="w-6 h-6 opcaity-50" />
                                                        Awaiting Deployment
                                                    </div>
                                                )}
                                            </div>

                                            {isComplete && (
                                                <div className="mt-4 pt-4 border-t border-white/10 flex justify-between items-center px-1">
                                                    <span className="text-[10px] uppercase tracking-widest text-slate-500 font-mono font-bold">Confidence Rating</span>
                                                    <div className="flex items-center gap-2">
                                                        <span className="text-xs text-emerald-400 font-mono font-bold">{Math.round(isComplete.confidence * 100)}%</span>
                                                        <div className="w-16 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                                                            <div
                                                                className={`h-full ${isComplete.confidence >= 0.7 ? "bg-emerald-500" : isComplete.confidence >= 0.4 ? "bg-amber-500" : "bg-red-500"}`}
                                                                style={{ width: `${isComplete.confidence * 100}%` }}
                                                            />
                                                        </div>
                                                    </div>
                                                </div>
                                            )}
                                        </motion.div>
                                    );
                                })}
                            </div>

                            {/* Final Acceptance Banner */}
                            <AnimatePresence>
                                {status === "complete" && (
                                    <motion.div
                                        initial={{ opacity: 0, y: 20 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        className="bg-emerald-500/10 border border-emerald-500/40 p-8 rounded-3xl flex flex-col md:flex-row items-center justify-between shadow-[0_0_50px_rgba(16,185,129,0.1)] gap-6"
                                    >
                                        <div className="text-center md:text-left">
                                            <h3 className="text-2xl font-black text-emerald-400 mb-2 flex items-center justify-center md:justify-start">
                                                <CheckCircle2 className="w-7 h-7 mr-3" /> System Consensus Reached
                                            </h3>
                                            <p className="text-emerald-100/70 font-medium">All autonomous agents have completed operations and cryptographic signatures are verified.</p>
                                        </div>
                                        <button
                                            onClick={handleAcceptAnalysis}
                                            className="px-8 py-4 bg-emerald-500 hover:bg-emerald-400 text-black rounded-full font-bold tracking-wide transition-all shadow-[0_0_20px_rgba(16,185,129,0.3)] hover:shadow-[0_0_30px_rgba(16,185,129,0.5)] flex items-center whitespace-nowrap group hover:scale-[1.02]"
                                        >
                                            View Final Report <ChevronRight className="w-5 h-5 ml-2 group-hover:translate-x-1 transition-transform" />
                                        </button>
                                    </motion.div>
                                )}
                            </AnimatePresence>
                        </motion.div>
                    )}
                </AnimatePresence>

                {/* HITL Intervention Dialog */}
                <Dialog open={!!hitlCheckpoint} onOpenChange={(o) => !o && dismissCheckpoint()}>
                    <DialogContent className="sm:max-w-md bg-slate-950 border border-amber-500/30 text-white shadow-[0_0_50px_rgba(245,158,11,0.1)]">
                        <DialogHeader>
                            <DialogTitle className="flex items-center text-amber-500 font-bold text-lg mb-2">
                                <AlertTriangle className="w-6 h-6 mr-3" />
                                Manual Override Required
                            </DialogTitle>
                            <DialogDescription className="text-slate-300 font-medium text-base">
                                Custom intervention triggered by <span className="text-white font-bold">{hitlCheckpoint?.agent_name}</span>.
                            </DialogDescription>
                        </DialogHeader>

                        <div className="bg-black/50 p-5 rounded-2xl border border-white/5 my-4">
                            <p className="text-sm font-mono text-amber-200/90 leading-relaxed whitespace-pre-wrap">
                                {hitlCheckpoint?.brief_text}
                            </p>
                        </div>

                        <DialogFooter className="flex-col sm:flex-row gap-3 pt-4 border-t border-white/5">
                            <button
                                onClick={() => handleHITLDecision('APPROVE')}
                                className="flex-1 px-4 py-3 rounded-xl bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30 font-bold flex items-center justify-center transition-colors"
                            >
                                <Check className="w-4 h-4 mr-2" /> Approve
                            </button>
                            <button
                                onClick={() => handleHITLDecision('REDIRECT')}
                                className="flex-1 px-4 py-3 rounded-xl bg-amber-500/20 text-amber-400 border border-amber-500/30 hover:bg-amber-500/30 font-bold flex items-center justify-center transition-colors"
                            >
                                <AlertCircle className="w-4 h-4 mr-2" /> Redirect
                            </button>
                            <button
                                onClick={() => handleHITLDecision('TERMINATE')}
                                className="flex-1 px-4 py-3 rounded-xl bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30 font-bold flex items-center justify-center transition-colors"
                            >
                                <X className="w-4 h-4 mr-2" /> Terminate
                            </button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            </main>
        </div>
    );
}
