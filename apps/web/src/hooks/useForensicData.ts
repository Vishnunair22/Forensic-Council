"use client";

import { useState, useEffect, useCallback } from "react";
import { Report, AgentResult } from "@/types";
import { HistorySchema, ReportSchema } from "@/lib/schemas";
import {
  ReportDTO,
  startInvestigation as apiStartInvestigation,
  InvestigationResponse,
  dbg
} from "@/lib/api";
import { ALLOWED_MIME_TYPES } from "@/lib/constants";
import { storage } from "@/lib/storage";

const HISTORY_KEY = "fc_history";
const CURRENT_REPORT_KEY = "fc_current_report";
const MAX_HISTORY_ITEMS = 20;

// Map backend ReportDTO to frontend Report format
export function mapReportDtoToReport(dto: ReportDTO): Report {
  const agentResults: AgentResult[] = [];

  // Flatten per-agent findings with deduplication transparency
  const seenKeys = new Set<string>();

  for (const [agentId, findings] of Object.entries(dto.per_agent_findings)) {
    for (const finding of findings) {
      const phase =
        ((finding.metadata as Record<string, unknown>)
          ?.analysis_phase as string) ?? "initial";
      const toolName =
        ((finding.metadata as Record<string, unknown>)?.tool_name as string) ??
        finding.finding_type;
      const dedupKey = `${agentId}:${finding.finding_type}:${toolName}`;

      const isDuplicate = seenKeys.has(dedupKey) && phase === "deep";
      seenKeys.add(dedupKey);
      const evidenceVerdict = finding.evidence_verdict ?? "INCONCLUSIVE";
      const confidence =
        evidenceVerdict === "NOT_APPLICABLE" || evidenceVerdict === "ERROR"
          ? 0
          : (finding.raw_confidence_score ??
            finding.confidence_raw ??
            0);

      agentResults.push({
        id: agentId,
        name: finding.agent_name,
        role: finding.agent_name,
        result: finding.court_statement || finding.reasoning_summary,
        confidence,
        thinking: finding.reasoning_summary,
        metadata: {
          ...finding.metadata,
          _deduplication: isDuplicate
            ? "confirmed_in_deep"
            : phase === "deep"
              ? "new_in_deep"
              : "initial",
        },
      });
    }
  }

  return {
    id: dto.report_id,
    fileName: dto.case_id,
    timestamp: dto.signed_utc ?? new Date().toISOString(),
    summary: dto.executive_summary,
    agents: agentResults,
    verdict: (dto.overall_verdict ?? "INCONCLUSIVE") as Report["verdict"],
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
    if (typeof window === "undefined") return;

    try {
      const savedHistory = storage.getItem<unknown>(HISTORY_KEY, true);
      const savedCurrent = storage.getItem<unknown>(CURRENT_REPORT_KEY, true);

      if (savedHistory) {
        const validated = HistorySchema.safeParse(savedHistory);
        if (validated.success) {
          setHistory(validated.data);
        }
      }

      if (savedCurrent) {
        const validated = ReportSchema.safeParse(savedCurrent);
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
    setHistory((prev) => {
      if (prev.some((h) => h.id === report.id)) return prev;
      const next = [report, ...prev].slice(0, MAX_HISTORY_ITEMS);
      if (typeof window !== "undefined") {
        try {
          storage.setItem(HISTORY_KEY, next, true);
        } catch {
          // Storage full — evict oldest entries and retry
          const trimmed = next.slice(0, Math.floor(MAX_HISTORY_ITEMS / 2));
          try {
            storage.setItem(HISTORY_KEY, trimmed, true);
          } catch {
            // Give up silently — the in-memory state is still correct
          }
          return trimmed;
        }
      }
      return next;
    });
  }, []);

  // Save current report
  const saveCurrentReport = useCallback((report: Report) => {
    setCurrentReport(report);
    if (typeof window !== "undefined") {
      storage.setItem(CURRENT_REPORT_KEY, report, true);
    }
  }, []);

  // Delete from history
  const deleteFromHistory = useCallback((id: string) => {
    setHistory((prev) => {
      const next = prev.filter((h) => h.id !== id);
      if (typeof window !== "undefined") {
        storage.setItem(HISTORY_KEY, next, true);
      }
      return next;
    });
  }, []);

  // Clear history
  const clearHistory = useCallback(() => {
    setHistory([]);
    if (typeof window !== "undefined") {
      storage.removeItem(HISTORY_KEY);
    }
  }, []);

  const validateFile = useCallback(
    (file: File): { valid: boolean; error?: string } => {
      const MAX_SIZE = 50 * 1024 * 1024; // 50 MB
      if (file.size > MAX_SIZE) {
        return { valid: false, error: "File exceeds 50MB limit." };
      }
      if (!ALLOWED_MIME_TYPES.has(file.type)) {
        return { valid: false, error: "Unsupported file type." };
      }
      return { valid: true };
    },
    [],
  );

  const startAnalysis = useCallback(
    async (
      file: File,
      caseId: string,
      investigatorId: string,
    ): Promise<string> => {
      setIsAnalyzing(true);
      setPollError(null);
      try {
        const resp: InvestigationResponse = await apiStartInvestigation(
          file,
          caseId,
          investigatorId,
        );
        return resp.session_id;
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Investigation failed";
        setPollError(msg);
        throw err;
      } finally {
        setIsAnalyzing(false);
      }
    },
    [],
  );

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
