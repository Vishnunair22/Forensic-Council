"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Report, AgentResult } from "@/types";
import { HistorySchema, ReportSchema } from "@/lib/schemas";
import { startInvestigation, getReport, ReportDTO, AgentFindingDTO } from "@/lib/api";

const HISTORY_KEY = "fc_history";
const CURRENT_REPORT_KEY = "fc_current_report";

// Map backend ReportDTO to frontend Report format
function mapReportDtoToReport(dto: ReportDTO): Report {
    const agentResults: AgentResult[] = [];
    
    // Flatten per-agent findings
    for (const [agentId, findings] of Object.entries(dto.per_agent_findings)) {
        for (const finding of findings) {
            agentResults.push({
                id: agentId,
                name: finding.agent_name,
                role: finding.agent_name,
                result: finding.court_statement || finding.reasoning_summary,
                confidence: finding.calibrated_probability ?? finding.confidence_raw,
                thinking: finding.reasoning_summary,
            });
        }
    }

    return {
        id: dto.report_id,
        fileName: dto.case_id,
        timestamp: dto.signed_utc,
        summary: dto.executive_summary,
        agents: agentResults,
    };
}

export const useForensicData = () => {
    const [history, setHistory] = useState<Report[]>([]);
    const [currentReport, setCurrentReport] = useState<Report | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isAnalyzing, setIsAnalyzing] = useState(false);
    const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
    const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    // Load data on mount (from localStorage for backward compatibility)
    useEffect(() => {
        if (typeof window === 'undefined') return;

        try {
            const savedHistory = localStorage.getItem(HISTORY_KEY);
            const savedCurrent = localStorage.getItem(CURRENT_REPORT_KEY);

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

        pollIntervalRef.current = setInterval(async () => {
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
                    setIsAnalyzing(false);
                    
                    // Save to localStorage for backward compatibility
                    if (typeof window !== 'undefined') {
                        localStorage.setItem(CURRENT_REPORT_KEY, JSON.stringify(report));
                    }
                }
            } catch (error) {
                console.error("Failed to poll for report:", error);
            }
        }, 5000); // Poll every 5 seconds
    }, []);

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
            localStorage.setItem(CURRENT_REPORT_KEY, JSON.stringify(report));
        }
    }, []);

    // Add to history
    const addToHistory = useCallback((report: Report) => {
        const newHistory = [report, ...history];
        setHistory(newHistory);
        if (typeof window !== 'undefined') {
            localStorage.setItem(HISTORY_KEY, JSON.stringify(newHistory));
        }
    }, [history]);

    // Delete from history
    const deleteFromHistory = useCallback((id: string) => {
        const newHistory = history.filter(h => h.id !== id);
        setHistory(newHistory);
        if (typeof window !== 'undefined') {
            localStorage.setItem(HISTORY_KEY, JSON.stringify(newHistory));
        }
    }, [history]);

    // Clear history
    const clearHistory = useCallback(() => {
        setHistory([]);
        if (typeof window !== 'undefined') {
            localStorage.removeItem(HISTORY_KEY);
        }
    }, []);

    // Client-side file validation
    const validateFile = useCallback((file: File): { valid: boolean; error?: string } => {
        const MAX_SIZE = 50 * 1024 * 1024; // 50MB
        const ALLOWED_TYPES = [
            "image/jpeg", "image/png", "image/webp", "image/gif",
            "video/mp4", "video/webm", "video/quicktime",
            "audio/wav", "audio/mpeg"
        ];

        if (file.size > MAX_SIZE) {
            return { valid: false, error: "File exceeds 50MB limit." };
        }
        if (!ALLOWED_TYPES.includes(file.type)) {
            return { valid: false, error: "Unsupported format. Use JPG, PNG, MP4, WAV, or MPEG." };
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
