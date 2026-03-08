"use client";

import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
    Upload, FileWarning, Fingerprint, Search, Shield, Activity,
    Bot, Database, FileDigit, Scan, Zap, Crosshair, ChevronRight, CheckCircle2, AlertTriangle, AlertCircle, X, Check, Loader2, Lightbulb, RotateCcw, ArrowRight, UploadCloud,
    BrainCircuit, Scale, FileText
} from "lucide-react";
import clsx from "clsx";
import { AgentResponseText } from "@/components/ui/AgentResponseText";
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
    const { addToHistory } = useForensicData();
    const { playSound } = useSound();

    const [file, setFile] = useState<File | null>(null);
    const [isDragging, setIsDragging] = useState(false);
    const [validationError, setValidationError] = useState<string | null>(null);

    // Server states
    const [isUploading, setIsUploading] = useState(false);
    const [sessionId, setSessionId] = useState<string | null>(null);
    const [uploadSuccessModalOpen, setUploadSuccessModalOpen] = useState(false);
    const [isTransitioningToResults, setIsTransitioningToResults] = useState(false);
    const [isSubmittingHITL, setIsSubmittingHITL] = useState(false);

    const {
        status,
        uiSequenceIndex,
        agentUpdates,
        completedAgents,
        startSimulation,
        connectWebSocket,
        resetSimulation: resetSimulationHook,
        hitlCheckpoint,
        errorMessage,
        dismissCheckpoint,
        resumeInvestigation,
        totalAgents
    } = useSimulation({
        playSound,
        onComplete: () => {
            // Let the user digest the page before automatically moving or showing a button
        }
    });

    const fileInputRef = useRef<HTMLInputElement>(null);

    // Memoize file preview URL to avoid memory leaks from creating new blob URLs on every render
    const filePreviewUrl = useMemo(() => {
        if (!file) return null;
        if (file.type.startsWith("image/") || file.type.startsWith("video/")) {
            return URL.createObjectURL(file);
        }
        return null;
    }, [file]);

    // Cleanup blob URL on unmount or when file changes
    useEffect(() => {
        return () => {
            if (filePreviewUrl) {
                URL.revokeObjectURL(filePreviewUrl);
            }
        };
    }, [filePreviewUrl]);

    const resetSimulation = useCallback(() => {
        setIsUploading(false);
        resetSimulationHook();
    }, [resetSimulationHook]);

    const triggerAnalysis = useCallback(async (targetFile: File) => {
        if (!targetFile) return;
        playSound("upload"); // Play upload sound at start
        setIsUploading(true);
        setValidationError(null);
        startSimulation(); // triggers setStatus("initiating") without setting a garbage ID

        try {
            const stored = localStorage.getItem("forensic_investigator_id");
            const validIdPattern = /^REQ-\d{5,10}$/;
            const investigatorId = (stored && validIdPattern.test(stored))
                ? stored
                : "REQ-" + (Math.floor(Math.random() * 900000) + 100000); // always 6 digits, safe range
            localStorage.setItem("forensic_investigator_id", investigatorId);
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
    }, [playSound, startSimulation, connectWebSocket, resetSimulation]);

    // Pick up the file injected by the landing page modal
    useEffect(() => {
        const pending = (window as any).__forensic_pending_file as File | undefined;
        if (pending) {
            delete (window as any).__forensic_pending_file;
            setFile(pending);
            // Auto-start analysis if the landing page requested it.
            // Small delay ensures the component is fully mounted and auth is ready.
            const autoStart = sessionStorage.getItem("forensic_auto_start");
            if (autoStart === "true") {
                sessionStorage.removeItem("forensic_auto_start");
                // 300 ms grace period for React hydration + auth token check
                setTimeout(() => triggerAnalysis(pending), 300);
            }
        } else if (sessionStorage.getItem("forensic_auto_start") === "true") {
            setValidationError("File was not received. Please re-select your evidence file.");
            sessionStorage.removeItem("forensic_auto_start");
        }
    }, [triggerAnalysis]);

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
        } else {
            playSound("error");
        }
    };

    const handleHITLDecision = async (decision: 'APPROVE' | 'REDIRECT' | 'TERMINATE') => {
        if (!hitlCheckpoint) return;
        setIsSubmittingHITL(true);
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
        } finally {
            setIsSubmittingHITL(false);
        }
    };

    const handleAcceptAnalysis = () => {
        playSound("click");
        setIsTransitioningToResults(true);
        setTimeout(() => {
            router.push("/result");
        }, 1000); // 1s transition
    };

    const validAgentsData = useMemo(() => {
        return AGENTS_DATA.filter(a => a.name !== "Council Arbiter");
    }, []);

    const validCompletedAgents = completedAgents.filter(c => validAgentsData.some(v => v.id === c.id));
    const progressPercentage = validAgentsData.length > 0 ? (validCompletedAgents.length / validAgentsData.length) * 100 : 0;

    const allAgentsDone = validAgentsData.length > 0 && validCompletedAgents.length >= validAgentsData.length;
    const showCompletionBanner = status === "complete" || allAgentsDone;

    // Track whether analysis has started — once true, keep the analysis panel
    // visible even if backend sends an error (so cards don't vanish mid-run).
    const hasStartedAnalysis = status === "analyzing" || status === "processing"
        || status === "complete" || completedAgents.length > 0
        || Object.keys(agentUpdates).length > 0
        || (status === "error" && (completedAgents.length > 0 || Object.keys(agentUpdates).length > 0));

    // Show the upload form only if truly idle (or error with no analysis started)
    const showUploadForm = (status === "idle" || (status === "error" && !hasStartedAnalysis)) && !isUploading;

    const activeAgentDef = AGENTS_DATA[uiSequenceIndex] || null;

    let progressText = "Awaiting deployment operations...";
    if (status === "initiating") {
        progressText = "Agents are currently initializing...";
    } else if (activeAgentDef && status !== "complete" && completedAgents.length < AGENTS_DATA.length) {
        // Show the active agent's current thinking text for richer feedback
        const activeData = agentUpdates[activeAgentDef.id];
        const thinkingSnippet = activeData?.thinking;
        if (thinkingSnippet && thinkingSnippet !== "Analyzing...") {
            progressText = `${activeAgentDef.name}: ${thinkingSnippet}`;
        } else {
            progressText = `${activeAgentDef.name} is analyzing evidence...`;
        }
    } else if (validCompletedAgents.length > 0 && status !== "complete") {
        progressText = `Gathering findings... (${validCompletedAgents.length}/${validAgentsData.length} complete)`;
    } else if (status === "complete") {
        progressText = "All agents have reported. Council Consensus reached.";
    }

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
                {showUploadForm && (
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
                    {showUploadForm && (
                        <motion.div
                            key="upload"
                            initial={{ opacity: 0, scale: 0.98 }}
                            animate={{ opacity: 1, scale: 1 }}
                            exit={{ opacity: 0, y: -20 }}
                            className="flex flex-col items-center justify-center min-h-[60vh] max-w-2xl mx-auto"
                        >
                            {/* The file was not picked on the landing page – show a slim inline upload */}
                            <div className="text-center mb-10">
                                <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/5 border border-white/10 text-sm text-cyan-400 backdrop-blur-md mb-6">
                                    <span className="relative flex h-2 w-2">
                                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
                                        <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500" />
                                    </span>
                                    Evidence Intake Terminal
                                </div>
                                <h1 className="text-4xl md:text-5xl font-black mb-4 tracking-tight">
                                    Initiate Investigation.
                                </h1>
                                <p className="text-slate-400 text-lg font-light max-w-md mx-auto">
                                    Deploy the <span className="text-emerald-400 font-medium">Council Autonomous Parsing System</span> on your digital artifact.
                                </p>
                            </div>

                            {file ? (
                                /* File selected inline – preview + action buttons */
                                <motion.div
                                    initial={{ opacity: 0, scale: 0.95 }}
                                    animate={{ opacity: 1, scale: 1 }}
                                    className="w-full rounded-[2rem] overflow-hidden
                                        bg-gradient-to-b from-white/[0.05] to-black/60
                                        border border-white/[0.10]
                                        shadow-[0_24px_60px_rgba(0,0,0,0.6),inset_0_1px_0_rgba(255,255,255,0.08)]
                                        backdrop-blur-3xl relative"
                                >
                                    <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/30 to-transparent" />

                                    {/* Preview */}
                                    <div className="relative w-full bg-black/40" style={{ minHeight: "200px" }}>
                                        {file.type.startsWith("image/") && (
                                            <img
                                                src={filePreviewUrl ?? ""}
                                                alt="Evidence"
                                                className="w-full max-h-72 object-contain"
                                            />
                                        )}
                                        {file.type.startsWith("video/") && (
                                            <video
                                                src={filePreviewUrl ?? ""}
                                                className="w-full max-h-72 object-contain"
                                                muted autoPlay loop playsInline
                                            />
                                        )}
                                        {!file.type.startsWith("image/") && !file.type.startsWith("video/") && (
                                            <div className="flex flex-col items-center justify-center h-52 gap-4">
                                                <div className="w-16 h-16 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center shadow-[0_0_20px_rgba(16,185,129,0.15)]">
                                                    {file.type.startsWith("audio/")
                                                        ? <span className="text-3xl">🎵</span>
                                                        : <span className="text-3xl">📄</span>
                                                    }
                                                </div>
                                                {file.type.startsWith("audio/") && (
                                                    <div className="flex items-end gap-1 h-8">
                                                        {[3, 7, 5, 9, 6, 4, 8, 5, 7, 3, 6, 8].map((h, i) => (
                                                            <motion.div
                                                                key={i}
                                                                className="w-1 bg-emerald-500/60 rounded-full"
                                                                animate={{ height: [`${h * 3}px`, `${h * 3 + 10}px`, `${h * 3}px`] }}
                                                                transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.08, ease: "easeInOut" }}
                                                            />
                                                        ))}
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                        {/* File info overlay */}
                                        <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/80 to-transparent px-6 py-4">
                                            <p className="text-sm font-mono text-white truncate font-semibold">{file.name}</p>
                                            <p className="text-[11px] text-slate-400 mt-0.5">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                                        </div>
                                    </div>

                                    {/* Buttons */}
                                    <div className="flex gap-3 p-6">
                                        <button
                                            onClick={() => { setFile(null); setValidationError(null); if (fileInputRef.current) fileInputRef.current.value = ""; }}
                                            className="flex-1 flex items-center justify-center gap-2 px-5 py-3.5 rounded-xl
                                                bg-white/[0.04] border border-white/[0.10] text-slate-300 font-semibold text-sm
                                                hover:bg-white/[0.08] hover:border-white/20 hover:text-white
                                                transition-all duration-200 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
                                        >
                                            <RotateCcw className="w-4 h-4 text-slate-400" />
                                            New Upload
                                        </button>
                                        <button
                                            onClick={() => triggerAnalysis(file!)}
                                            className="flex-1 flex items-center justify-center gap-2 px-5 py-3.5 rounded-xl
                                                bg-gradient-to-r from-emerald-500 to-cyan-500 text-white font-bold text-sm
                                                hover:from-emerald-400 hover:to-cyan-400
                                                hover:scale-[1.02] hover:shadow-[0_0_30px_rgba(16,185,129,0.4)]
                                                transition-all duration-200
                                                shadow-[0_4px_20px_rgba(16,185,129,0.25),inset_0_1px_0_rgba(255,255,255,0.2)]
                                                border border-white/[0.15]"
                                        >
                                            Initiate Analysis
                                            <ArrowRight className="w-4 h-4" />
                                        </button>
                                    </div>
                                </motion.div>
                            ) : (
                                /* Drop zone */
                                <div
                                    onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                                    onDragLeave={() => setIsDragging(false)}
                                    onDrop={(e) => { e.preventDefault(); setIsDragging(false); if (e.dataTransfer.files?.[0]) handleFile(e.dataTransfer.files[0]); }}
                                    onClick={() => fileInputRef.current?.click()}
                                    className={clsx(
                                        "w-full py-20 rounded-[2rem] border-2 border-dashed flex flex-col items-center justify-center cursor-pointer transition-all duration-300 group relative overflow-hidden backdrop-blur-sm",
                                        isDragging
                                            ? "border-cyan-400/60 bg-cyan-500/[0.04]"
                                            : "border-white/10 bg-white/[0.02] hover:border-emerald-500/40 hover:bg-emerald-500/[0.02]"
                                    )}
                                >
                                    <input
                                        type="file"
                                        ref={fileInputRef}
                                        onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
                                        className="hidden"
                                        accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.txt"
                                    />
                                    <motion.div
                                        animate={{ scale: isDragging ? 1.12 : 1 }}
                                        className="w-20 h-20 rounded-2xl bg-gradient-to-br from-emerald-500/15 to-cyan-600/10 border border-emerald-500/20 flex items-center justify-center mb-5 shadow-[0_0_30px_rgba(16,185,129,0.15)] relative"
                                    >
                                        <div className="absolute inset-[-8px] rounded-[24px] border border-emerald-500/10 border-dashed animate-[spin_8s_linear_infinite]" />
                                        <UploadCloud className={clsx("w-9 h-9 transition-colors", isDragging ? "text-cyan-300" : "text-emerald-400 group-hover:text-emerald-300")} />
                                    </motion.div>
                                    <h3 className="text-xl font-bold text-white mb-2">Drop evidence file here</h3>
                                    <p className="text-slate-500 text-sm font-mono">or click to browse</p>
                                </div>
                            )}

                            <AnimatePresence>
                                {(validationError || errorMessage) && (
                                    <motion.div
                                        initial={{ opacity: 0, y: 8 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        exit={{ opacity: 0 }}
                                        className="mt-5 flex items-center text-red-400 bg-red-500/10 px-5 py-3 rounded-xl border border-red-500/20"
                                    >
                                        <FileWarning className="w-5 h-5 mr-3 shrink-0" />
                                        <span className="text-sm font-medium">{validationError || errorMessage}</span>
                                    </motion.div>
                                )}
                            </AnimatePresence>
                        </motion.div>
                    )}

                    {(hasStartedAnalysis || isUploading || (status !== "idle" && status !== "error")) && (
                        <motion.div
                            key="analysis"
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="w-full flex flex-col pt-4 max-w-4xl mx-auto"
                        >
                            {/* ── TOP: Evidence Intake Title ── */}
                            <div className="text-center mb-10">
                                <motion.p
                                    initial={{ opacity: 0, y: -8 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    className="text-xs font-mono uppercase tracking-[0.3em] text-emerald-500/70 mb-3"
                                >
                                    ◈ Active Investigation
                                </motion.p>
                                <motion.h1
                                    initial={{ opacity: 0, y: -8 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ delay: 0.1 }}
                                    className="text-4xl md:text-5xl font-black tracking-tight text-white mb-3"
                                >
                                    Evidence Intake
                                </motion.h1>
                                {file && (
                                    <motion.p
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 1 }}
                                        transition={{ delay: 0.2 }}
                                        className="text-slate-400 font-mono text-sm truncate max-w-md mx-auto bg-white/[0.04] border border-white/[0.08] px-4 py-2 rounded-full"
                                    >
                                        📎 {file.name}
                                    </motion.p>
                                )}
                            </div>

                            {/* ── DYNAMIC STATUS INDICATOR ── */}
                            <motion.div
                                initial={{ opacity: 0, scale: 0.96 }}
                                animate={{ opacity: 1, scale: 1 }}
                                transition={{ delay: 0.15 }}
                                className="relative rounded-2xl border border-white/[0.08] bg-white/[0.02] backdrop-blur-xl p-6 mb-10 flex items-center gap-5 overflow-hidden shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]"
                            >
                                <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/15 to-transparent" />
                                {/* Animated glow behind indicator */}
                                <div className="absolute left-0 top-0 bottom-0 w-32 bg-gradient-to-r from-emerald-500/10 to-transparent pointer-events-none" />

                                {/* Multi-state icon */}
                                <div className="relative shrink-0">
                                    <AnimatePresence mode="wait">
                                        {status === "complete" ? (
                                            <motion.div
                                                key="complete"
                                                initial={{ scale: 0, rotate: -20 }}
                                                animate={{ scale: 1, rotate: 0 }}
                                                exit={{ scale: 0 }}
                                                className="w-14 h-14 rounded-2xl bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center shadow-[0_0_20px_rgba(16,185,129,0.3)]"
                                            >
                                                <CheckCircle2 className="w-7 h-7 text-emerald-400" />
                                            </motion.div>
                                        ) : isUploading ? (
                                            <motion.div
                                                key="uploading"
                                                initial={{ scale: 0 }}
                                                animate={{ scale: 1 }}
                                                exit={{ scale: 0 }}
                                                className="w-14 h-14 rounded-2xl bg-cyan-500/15 border border-cyan-500/30 flex items-center justify-center"
                                            >
                                                <Loader2 className="w-7 h-7 text-cyan-400 animate-spin" />
                                            </motion.div>
                                        ) : (
                                            <motion.div
                                                key="thinking"
                                                initial={{ scale: 0 }}
                                                animate={{ scale: 1 }}
                                                exit={{ scale: 0 }}
                                                className="w-14 h-14 rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center relative"
                                            >
                                                {/* Pulsing rings */}
                                                <motion.div
                                                    animate={{ scale: [1, 1.5, 1], opacity: [0.3, 0, 0.3] }}
                                                    transition={{ duration: 2, repeat: Infinity, ease: "easeOut" }}
                                                    className="absolute inset-0 rounded-2xl border border-amber-400/30"
                                                />
                                                <Lightbulb className="w-7 h-7 text-amber-400 animate-pulse" />
                                            </motion.div>
                                        )}
                                    </AnimatePresence>
                                </div>

                                {/* Dynamic text */}
                                <div className="flex-1 min-w-0">
                                    <AnimatePresence mode="wait">
                                        <motion.p
                                            key={progressText}
                                            initial={{ opacity: 0, x: 10 }}
                                            animate={{ opacity: 1, x: 0 }}
                                            exit={{ opacity: 0, x: -10 }}
                                            transition={{ duration: 0.25 }}
                                            className="text-white font-bold text-lg md:text-xl tracking-tight"
                                        >
                                            {progressText}
                                        </motion.p>
                                    </AnimatePresence>
                                    {/* Progress bar */}
                                    <div className="mt-3 w-full h-1.5 bg-black/60 rounded-full overflow-hidden border border-white/5">
                                        <motion.div
                                            initial={{ width: 0 }}
                                            animate={{ width: `${progressPercentage}%` }}
                                            transition={{ duration: 0.8, ease: "circOut" }}
                                            className={`h-full rounded-full ${status === "complete" ? "bg-emerald-400" : "bg-gradient-to-r from-emerald-500 to-cyan-400"} shadow-[0_0_10px_rgba(16,185,129,0.5)]`}
                                        />
                                    </div>
                                    <div className="flex justify-between mt-1">
                                        <span className="text-[10px] font-mono text-slate-600 uppercase tracking-widest">Council Progress</span>
                                        <span className="text-[10px] font-mono text-emerald-500 font-bold">{Math.round(progressPercentage)}%</span>
                                    </div>
                                </div>
                            </motion.div>

                            {/* ── INLINE ERROR BANNER (shows inside analysis, not upload form) ── */}
                            {status === "error" && errorMessage && hasStartedAnalysis && (
                                <motion.div
                                    initial={{ opacity: 0, y: -8 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    className="mb-6 flex items-center bg-red-500/10 border border-red-500/20 rounded-xl px-5 py-4"
                                >
                                    <FileWarning className="w-5 h-5 text-red-400 mr-3 shrink-0" />
                                    <span className="text-sm text-red-300 flex-1">{errorMessage}</span>
                                    <button
                                        onClick={() => { resetSimulation(); }}
                                        className="ml-4 text-xs font-mono text-red-400 hover:text-red-300 underline"
                                    >
                                        Try Again
                                    </button>
                                </motion.div>
                            )}

                            {/* ── COUNCIL HUB: ALL AGENTS AROUND THE EVIDENCE ── */}
                            <div className="relative w-full aspect-square max-w-[600px] mx-auto mb-12 flex items-center justify-center">
                                {/* Background glow / rings */}
                                <div className="absolute inset-0 flex items-center justify-center">
                                    <div className="w-[80%] h-[80%] rounded-full border border-white/5 animate-[pulse_4s_infinite]" />
                                    <div className="w-[60%] h-[60%] rounded-full border border-white/10 animate-[pulse_3s_infinite]" />
                                    <div className="w-[40%] h-[40%] rounded-full border border-emerald-500/10 animate-[pulse_2s_infinite]" />
                                </div>

                                {/* Central Evidence Node */}
                                <div className="relative z-20 w-32 h-32 md:w-40 md:h-40 rounded-3xl overflow-hidden shadow-[0_0_50px_rgba(16,185,129,0.3)] border-2 border-emerald-500/30 bg-black/80 flex items-center justify-center group transition-transform duration-500 hover:scale-105">
                                    {filePreviewUrl ? (
                                        <img src={filePreviewUrl} alt="Evidence" className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity" />
                                    ) : (
                                        <Shield className="w-12 h-12 text-emerald-500 animate-pulse" />
                                    )}
                                    <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent flex items-end justify-center pb-3">
                                        <span className="text-[10px] font-mono text-emerald-400 uppercase tracking-widest font-bold">Evidence</span>
                                    </div>
                                </div>

                                {/* Agents arranged in a circle */}
                                {validAgentsData.map((agent, i) => {
                                    const total = validAgentsData.length;
                                    const angle = (i * 360) / total - 90; // Start at top
                                    const radius = typeof window !== 'undefined' && window.innerWidth < 640 ? 120 : 180;
                                    const x = Math.cos((angle * Math.PI) / 180) * radius;
                                    const y = Math.sin((angle * Math.PI) / 180) * radius;

                                    const isComplete = completedAgents.find((a: any) => a.id === agent.id);
                                    const isActive = uiSequenceIndex === i && !isComplete;
                                    const agentState = agentUpdates[agent.id];

                                    return (
                                        <motion.div
                                            key={agent.id}
                                            initial={{ opacity: 0, scale: 0.5 }}
                                            animate={{
                                                opacity: 1,
                                                scale: 1,
                                                x: x,
                                                y: y
                                            }}
                                            transition={{ delay: i * 0.1, type: "spring", stiffness: 100 }}
                                            className="absolute flex flex-col items-center"
                                        >
                                            {/* Agent Node */}
                                            <div className="relative group cursor-help">
                                                {/* Connecting Line (Visual) */}
                                                <div
                                                    className={`absolute top-1/2 left-1/2 -z-10 h-0.5 bg-gradient-to-r from-emerald-500/30 to-transparent transition-all duration-700 origin-left`}
                                                    style={{
                                                        width: radius,
                                                        transform: `rotate(${angle + 180}deg)`,
                                                        opacity: isActive || isComplete ? 1 : 0.2
                                                    }}
                                                />

                                                <div className={clsx(
                                                    "w-16 h-16 rounded-2xl border flex items-center justify-center transition-all duration-500",
                                                    "bg-black/60 shadow-xl backdrop-blur-md",
                                                    isComplete
                                                        ? "border-emerald-500 shadow-[0_0_20px_rgba(16,185,129,0.3)] ring-1 ring-emerald-500/50"
                                                        : isActive
                                                            ? "border-amber-500 shadow-[0_0_20px_rgba(245,158,11,0.2)] scale-110 animate-pulse ring-1 ring-amber-500/50"
                                                            : "border-white/10 opacity-60"
                                                )}>
                                                    <AgentIcon role={agent.role} active={isActive} />
                                                </div>

                                                {/* Agent Label */}
                                                <div className="absolute -top-10 left-1/2 -translate-x-1/2 whitespace-nowrap">
                                                    <span className={clsx(
                                                        "text-[9px] font-mono uppercase tracking-[0.2em] font-black px-2 py-0.5 rounded border transition-colors",
                                                        isComplete ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/5" : "text-white/60 border-white/5"
                                                    )}>
                                                        {agent.name.split(" ")[0]}
                                                    </span>
                                                </div>

                                                {/* Live Status Text (Transparency) */}
                                                <AnimatePresence>
                                                    {(isActive || (isComplete && agentState?.thinking)) && (
                                                        <motion.div
                                                            initial={{ opacity: 0, scale: 0.8, y: 10 }}
                                                            animate={{ opacity: 1, scale: 1, y: 0 }}
                                                            exit={{ opacity: 0, scale: 0.8 }}
                                                            className="absolute top-16 left-1/2 -translate-x-1/2 mt-4 z-30"
                                                        >
                                                            <div className="bg-black/90 border border-white/10 rounded-lg py-1.5 px-3 shadow-2xl min-w-[140px] text-center backdrop-blur-xl">
                                                                <p className="text-[10px] font-mono text-emerald-400 truncate max-w-[180px]">
                                                                    {isActive ? (agentState?.thinking || "Initializing...") : "Analysis Verified"}
                                                                </p>
                                                            </div>
                                                            {/* Arrow */}
                                                            <div className="w-2 h-2 bg-black border-l border-t border-white/10 rotate-45 absolute -top-1 left-1/2 -translate-x-1/2" />
                                                        </motion.div>
                                                    )}
                                                </AnimatePresence>

                                                {/* Confidence ring when complete */}
                                                {isComplete && (
                                                    <div className="absolute -inset-2 rounded-[22px] border-2 border-emerald-500/20 animate-[ping_3s_infinite]" />
                                                )}
                                            </div>
                                        </motion.div>
                                    );
                                })}
                            </div>

                            {/* ── DEEP ANALYSIS CONTROL PANEL (Decision Dialog Replacement) ── */}
                            <AnimatePresence>
                                {status === "awaiting_decision" && (
                                    <motion.div
                                        initial={{ opacity: 0, y: 30 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        exit={{ opacity: 0, y: 20 }}
                                        className="relative z-50 max-w-2xl mx-auto"
                                    >
                                        <div className="bg-gradient-to-b from-slate-900/95 to-black/95 border border-emerald-500/30 rounded-3xl p-8 shadow-[0_0_100px_rgba(16,185,129,0.15)] backdrop-blur-2xl">
                                            <div className="flex flex-col md:flex-row items-center gap-6 mb-8">
                                                <div className="w-16 h-16 rounded-2xl bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center shrink-0">
                                                    <CheckCircle2 className="w-8 h-8 text-emerald-400" />
                                                </div>
                                                <div className="text-center md:text-left">
                                                    <h2 className="text-2xl font-black text-white tracking-tight">Initial Analysis Complete</h2>
                                                    <p className="text-slate-400 text-sm mt-1">
                                                        The Council has completed the first forensic sweep. You can now examine the preliminary findings or trigger a Deep Neural investigation for court-grade accuracy.
                                                    </p>
                                                </div>
                                            </div>

                                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                                <button
                                                    onClick={() => resumeInvestigation(false)}
                                                    className="group relative flex flex-col items-start p-5 rounded-2xl bg-white/[0.03] border border-white/10 transition-all hover:bg-white/[0.06] hover:border-white/20"
                                                >
                                                    <div className="flex items-center gap-2 mb-2">
                                                        <FileText className="w-4 h-4 text-slate-400" />
                                                        <span className="text-sm font-bold text-white uppercase tracking-wider">Fast Track</span>
                                                    </div>
                                                    <span className="text-xs text-slate-500 leading-relaxed text-left">
                                                        Skip heavy ML models. Generate report now using existing forensic data.
                                                    </span>
                                                    <div className="mt-4 flex items-center gap-2 text-emerald-400 font-bold text-sm">
                                                        Proceed with analysis <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                                                    </div>
                                                </button>

                                                <button
                                                    onClick={() => resumeInvestigation(true)}
                                                    className="group relative flex flex-col items-start p-5 rounded-2xl bg-emerald-500/5 border border-emerald-500/20 transition-all hover:bg-emerald-500/10 hover:border-emerald-500/40 shadow-[inset_0_0_20px_rgba(16,185,129,0.02)]"
                                                >
                                                    <div className="flex items-center gap-2 mb-2">
                                                        <Zap className="w-4 h-4 text-emerald-400" />
                                                        <span className="text-sm font-bold text-emerald-400 uppercase tracking-wider">Neural Deep Pass</span>
                                                    </div>
                                                    <span className="text-xs text-slate-400 leading-relaxed text-left">
                                                        Run heavy AI models (YOLO, CLIP, EasyOCR) for exhaustive artifact detection.
                                                    </span>
                                                    <div className="mt-4 flex items-center gap-2 text-emerald-400 font-bold text-sm">
                                                        Trigger Deep Analysis <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                                                    </div>
                                                    <div className="absolute top-4 right-4 text-[10px] font-mono text-emerald-600 font-bold uppercase tracking-widest bg-emerald-500/10 px-2 py-0.5 rounded">
                                                        +400s wait
                                                    </div>
                                                </button>
                                            </div>
                                        </div>
                                    </motion.div>
                                )}
                            </AnimatePresence>

                            {/* ── FINAL COMPLETION ACTIONS ── */}
                            <AnimatePresence>
                                {(status === "complete" || allAgentsDone) && (
                                    <motion.div
                                        initial={{ opacity: 0, y: 20 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        className="mt-12 p-8 rounded-3xl bg-gradient-to-br from-white/[0.03] to-transparent border border-white/[0.08] backdrop-blur-xl flex flex-col md:flex-row items-center justify-between gap-8"
                                    >
                                        <div className="flex flex-col gap-2">
                                            <div className="flex items-center gap-3">
                                                <div className="w-8 h-8 rounded-full bg-emerald-500/20 flex items-center justify-center shrink-0">
                                                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                                                </div>
                                                <h3 className="text-xl font-black text-emerald-400">Council Consensus Reached</h3>
                                            </div>
                                            <p className="text-slate-400 text-sm font-medium">
                                                All {validAgentsData.length} agents have completed analysis. Cryptographic signatures verified.
                                            </p>
                                        </div>

                                        <div className="relative z-10 flex flex-col sm:flex-row gap-3 w-full md:w-auto">
                                            {/* Analyse Again */}
                                            <button
                                                onClick={() => { playSound("click"); window.location.reload(); }}
                                                className="flex items-center justify-center gap-2.5 px-6 py-3.5 rounded-xl
                                                    bg-white/[0.04] border border-white/[0.10] text-slate-300 font-semibold
                                                    hover:bg-white/[0.08] hover:border-white/20 hover:text-white
                                                    transition-all duration-200 whitespace-nowrap
                                                    shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
                                            >
                                                <RotateCcw className="w-4 h-4 text-slate-400" />
                                                Analyse Again
                                            </button>
                                            {/* Accept Analysis */}
                                            <button
                                                onClick={handleAcceptAnalysis}
                                                className="flex items-center justify-center gap-2.5 px-6 py-3.5 rounded-xl
                                                    bg-gradient-to-r from-emerald-500 to-cyan-500 text-white font-bold
                                                    hover:from-emerald-400 hover:to-cyan-400
                                                    hover:scale-[1.02] hover:shadow-[0_0_30px_rgba(16,185,129,0.5)]
                                                    transition-all duration-200 whitespace-nowrap
                                                    shadow-[0_4px_20px_rgba(16,185,129,0.3),inset_0_1px_0_rgba(255,255,255,0.2)]
                                                    border border-white/[0.15]"
                                            >
                                                Accept Analysis
                                                <ArrowRight className="w-4 h-4" />
                                            </button>
                                        </div>
                                    </motion.div>
                                )}
                            </AnimatePresence>
                        </motion.div>
                    )}
                </AnimatePresence>

                {/* Transition Overlay to Results */}
                <AnimatePresence>
                    {isTransitioningToResults && (
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            className="fixed inset-0 z-[100] bg-black/90 backdrop-blur-xl flex flex-col items-center justify-center"
                        >
                            <motion.div
                                initial={{ scale: 0.8, opacity: 0 }}
                                animate={{ scale: 1, opacity: 1 }}
                                transition={{ delay: 0.2, type: "spring" }}
                                className="flex flex-col items-center text-center p-8 max-w-lg"
                            >
                                <div className="relative mb-8">
                                    <div className="absolute inset-0 bg-emerald-500/20 blur-[50px] rounded-full animate-pulse" />
                                    <Bot className="w-20 h-20 text-emerald-400 relative z-10" />
                                </div>
                                <motion.h2
                                    initial={{ y: 10, opacity: 0 }}
                                    animate={{ y: 0, opacity: 1 }}
                                    transition={{ delay: 0.4 }}
                                    className="text-3xl font-black text-white mb-4 tracking-tight"
                                >
                                    Synthesizing Intelligence
                                </motion.h2>
                                <motion.p
                                    initial={{ y: 10, opacity: 0 }}
                                    animate={{ y: 0, opacity: 1 }}
                                    transition={{ delay: 0.6 }}
                                    className="text-emerald-400 font-mono text-sm uppercase tracking-widest flex items-center justify-center gap-3"
                                >
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                    Arbiter Agent is compiling analysis into final results...
                                </motion.p>
                                <motion.div
                                    initial={{ width: 0 }}
                                    animate={{ width: "100%" }}
                                    transition={{ delay: 0.8, duration: 1.5, ease: "easeInOut" }}
                                    className="h-1 bg-emerald-500 rounded-full mt-8 shadow-[0_0_15px_rgba(16,185,129,0.5)]"
                                />
                            </motion.div>
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
                                disabled={isSubmittingHITL}
                                className="flex-1 px-4 py-3 rounded-xl bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30 font-bold flex items-center justify-center transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {isSubmittingHITL ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Check className="w-4 h-4 mr-2" />} Approve
                            </button>
                            <button
                                onClick={() => handleHITLDecision('REDIRECT')}
                                disabled={isSubmittingHITL}
                                className="flex-1 px-4 py-3 rounded-xl bg-amber-500/20 text-amber-400 border border-amber-500/30 hover:bg-amber-500/30 font-bold flex items-center justify-center transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {isSubmittingHITL ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <AlertCircle className="w-4 h-4 mr-2" />} Redirect
                            </button>
                            <button
                                onClick={() => handleHITLDecision('TERMINATE')}
                                disabled={isSubmittingHITL}
                                className="flex-1 px-4 py-3 rounded-xl bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30 font-bold flex items-center justify-center transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {isSubmittingHITL ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <X className="w-4 h-4 mr-2" />} Terminate
                            </button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            </main>
        </div>
    );
}
