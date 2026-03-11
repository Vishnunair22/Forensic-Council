"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Report, AgentResult } from "@/types";
import { HistorySchema, ReportSchema } from "@/lib/schemas";
import { startInvestigation, getReport, ReportDTO } from "@/lib/api";
import { ALLOWED_MIME_TYPES } from "@/lib/constants";

const HISTORY_KEY = "fc_history";
const CURRENT_REPORT_KEY = "fc_current_report";

// Map backend ReportDTO to frontend Report format
export function mapReportDtoToReport(dto: ReportDTO): Report {
    const agentResults: AgentResult[] = [];

    // Flatten per-agent findings
    for (const [agentId, findings] of Object.entries(dto.per_agent_findings)) {
        for (const finding of findings) {
            agentResults.push({
                id: agentId,
                name: finding.agent_name,
                role: finding.agent_name,
                result: finding.court_statement || finding.reasoning_summary,
                confidence: finding.calibrated_probability ?? (finding.confidence_raw || 1.0),
                thinking: finding.reasoning_summary,
            });
        }
    }

    return {
        id: dto.report_id,
        fileName: dto.case_id,
        timestamp: dto.signed_utc ?? new Date().toISOString(),
        summary: dto.executive_summary,
        agents: agentResults,
    };
}

export const useForensicData = () => {
    const [history, setHistory] = useState<Report[]>([]);
    const [currentReport, setCurrentReport] = useState<Report | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isAnalyzing, setIsAnalyzing] = useState(false);
    const [pollError, setPollError] = useState<string | null>(null);
    const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
    const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    // Load data on mount (from sessionStorage for sensitive data)
    useEffect(() => {
        if (typeof window === 'undefined') return;

        try {
            const savedHistory = sessionStorage.getItem(HISTORY_KEY);
            const savedCurrent = sessionStorage.getItem(CURRENT_REPORT_KEY);

            if (savedHistory) {
                const parsed = JSON.parse(savedHistory);
                const validated = HistorySchema.safeParse(parsed);
                if (validated.success) {
                    setHistory(validated.data);
                }
            }

            if (savedCurrent) {
                const parsed = JSON.parse(savedCurrent);
                const validated = ReportSchema.safeParse(parsed);
                if (validated.success) {
                    setCurrentReport(validated.data);
                }
            }
        } catch (error) {
            console.error("Failed to load forensic data", error);
        } finally {
            setIsLoading(false);
        }
    }, []);

    // Add to history - defined first so it can be used in pollForReport
    const addToHistory = useCallback((report: Report) => {
        setHistory(prev => {
            if (prev.some(h => h.id === report.id)) return prev;
            const next = [report, ...prev];
            if (typeof window !== 'undefined') {
                sessionStorage.setItem(HISTORY_KEY, JSON.stringify(next));
            }
            return next;
        });
    }, []);

    // Start analysis - calls the real API
    const startAnalysis = useCallback(async (
        file: File,
        caseId: string,
        investigatorId: string
    ): Promise<string> => {
        setIsAnalyzing(true);

        try {
            const result = await startInvestigation(file, caseId, investigatorId);
            setCurrentSessionId(result.session_id);
            return result.session_id;
        } catch (error) {
            console.error("Failed to start investigation:", error);
            throw error;
        }
    }, []);

    // Poll for report completion
    const pollForReport = useCallback(async (sessionId: string): Promise<void> => {
        // Clear any existing poll
        if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current);
        }
        setPollError(null);

        const MAX_POLL_ATTEMPTS = 60; // 5 min at 5s interval
        let attempts = 0;

        pollIntervalRef.current = setInterval(async () => {
            attempts++;
            if (attempts > MAX_POLL_ATTEMPTS) {
                if (pollIntervalRef.current) {
                    clearInterval(pollIntervalRef.current);
                    pollIntervalRef.current = null;
                }
                setIsAnalyzing(false);
                setPollError("Analysis timed out. The investigation took too long.");
                return;
            }

            try {
                const result = await getReport(sessionId);

                if (result.status === "complete" && result.report) {
                    // Stop polling
                    if (pollIntervalRef.current) {
                        clearInterval(pollIntervalRef.current);
                        pollIntervalRef.current = null;
                    }

                    // Map to frontend format
                    const report = mapReportDtoToReport(result.report);
                    setCurrentReport(report);
                    addToHistory(report); // Save to History tab
                    setIsAnalyzing(false);

                    // Save to sessionStorage (sensitive data should not persist)
                    if (typeof window !== 'undefined') {
                        sessionStorage.setItem(CURRENT_REPORT_KEY, JSON.stringify(report));
                    }
                }
            } catch (error) {
                console.error("Failed to poll for report:", error);
                if (pollIntervalRef.current) {
                    clearInterval(pollIntervalRef.current);
                    pollIntervalRef.current = null;
                }
                setIsAnalyzing(false);
                setPollError(error instanceof Error ? error.message : "Failed to retrieve analysis results.");
            }
        }, 5000); // Poll every 5 seconds
    }, [addToHistory]);

    // Get current report
    const getCurrentReport = useCallback((): Report | null => {
        return currentReport;
    }, [currentReport]);

    // Get history
    const getHistory = useCallback((): Report[] => {
        return history;
    }, [history]);

    // Save current report
    const saveCurrentReport = useCallback((report: Report) => {
        setCurrentReport(report);
        if (typeof window !== 'undefined') {
            sessionStorage.setItem(CURRENT_REPORT_KEY, JSON.stringify(report));
        }
    }, []);

    // Delete from history
    const deleteFromHistory = useCallback((id: string) => {
        const newHistory = history.filter(h => h.id !== id);
        setHistory(newHistory);
        if (typeof window !== 'undefined') {
            sessionStorage.setItem(HISTORY_KEY, JSON.stringify(newHistory));
        }
    }, [history]);

    // Clear history
    const clearHistory = useCallback(() => {
        setHistory([]);
        if (typeof window !== 'undefined') {
            sessionStorage.removeItem(HISTORY_KEY);
        }
    }, []);

    // Client-side file validation
    const validateFile = useCallback((file: File): { valid: boolean; error?: string } => {
        const MAX_SIZE = 50 * 1024 * 1024; // 50MB

        if (file.size > MAX_SIZE) {
            return { valid: false, error: "File exceeds 50MB limit." };
        }
        if (!ALLOWED_MIME_TYPES.has(file.type)) {
            return { valid: false, error: "Unsupported format." };
        }
        return { valid: true };
    }, []);

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            if (pollIntervalRef.current) {
                clearInterval(pollIntervalRef.current);
            }
        };
    }, []);

    return {
        history,
        currentReport,
        isLoading,
        isAnalyzing,
        pollError,
        currentSessionId,
        startAnalysis,
        pollForReport,
        getCurrentReport,
        getHistory,
        saveCurrentReport,
        addToHistory,
        deleteFromHistory,
        clearHistory,
        validateFile
    };
};
