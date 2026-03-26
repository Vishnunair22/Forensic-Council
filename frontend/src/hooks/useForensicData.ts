"use client";

import { useState, useEffect, useCallback } from "react";
import { Report, AgentResult } from "@/types";
import { HistorySchema, ReportSchema } from "@/lib/schemas";
import { ReportDTO } from "@/lib/api";

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

    return {
        history,
        currentReport,
        isLoading,
        saveCurrentReport,
        addToHistory,
        deleteFromHistory,
        clearHistory,
    };
};
