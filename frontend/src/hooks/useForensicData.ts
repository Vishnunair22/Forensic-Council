"use client";

import { useState, useEffect, useCallback } from "react";
import { Report, AgentResult } from "@/types";
import { HistorySchema, ReportSchema } from "@/lib/schemas";
import { ReportDTO, startInvestigation as apiStartInvestigation, InvestigationResponse } from "@/lib/api";
import { ALLOWED_MIME_TYPES } from "@/lib/constants";

/** Dev-only logger — silenced in production builds */
const isDev = process.env.NODE_ENV !== "production";
const dbg = {
    error: isDev ? console.error.bind(console) : () => {},
};

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
                confidence: finding.raw_confidence_score ?? finding.calibrated_probability ?? (finding.confidence_raw || 1.0),
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
            dbg.error("Failed to load forensic data", error);
        } finally {
            setIsLoading(false);
        }
    }, []);

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

    // Save current report
    const saveCurrentReport = useCallback((report: Report) => {
        setCurrentReport(report);
        if (typeof window !== 'undefined') {
            sessionStorage.setItem(CURRENT_REPORT_KEY, JSON.stringify(report));
        }
    }, []);

    // Delete from history
    const deleteFromHistory = useCallback((id: string) => {
        setHistory(prev => {
            const next = prev.filter(h => h.id !== id);
            if (typeof window !== 'undefined') {
                sessionStorage.setItem(HISTORY_KEY, JSON.stringify(next));
            }
            return next;
        });
    }, []);

    // Clear history
    const clearHistory = useCallback(() => {
        setHistory([]);
        if (typeof window !== 'undefined') {
            sessionStorage.removeItem(HISTORY_KEY);
        }
    }, []);

    const validateFile = useCallback((file: File): { valid: boolean; error?: string } => {
        const MAX_SIZE = 50 * 1024 * 1024; // 50 MB
        if (file.size > MAX_SIZE) {
            return { valid: false, error: "File exceeds 50MB limit." };
        }
        if (!ALLOWED_MIME_TYPES.has(file.type)) {
            return { valid: false, error: "Unsupported file type." };
        }
        return { valid: true };
    }, []);

    const startAnalysis = useCallback(async (
        file: File,
        caseId: string,
        investigatorId: string,
    ): Promise<string> => {
        setIsAnalyzing(true);
        setPollError(null);
        try {
            const resp: InvestigationResponse = await apiStartInvestigation(file, caseId, investigatorId);
            return resp.session_id;
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : "Investigation failed";
            setPollError(msg);
            throw err;
        } finally {
            setIsAnalyzing(false);
        }
    }, []);

    return {
        history,
        currentReport,
        isLoading,
        isAnalyzing,
        pollError,
        saveCurrentReport,
        addToHistory,
        deleteFromHistory,
        clearHistory,
        validateFile,
        startAnalysis,
    };
};
