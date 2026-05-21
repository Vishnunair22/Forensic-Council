"use client";

import React from "react";
import { Home as HomeIcon, Plus, Download } from "lucide-react";
import { API_BASE } from "@/lib/api";
import { toast } from "@/hooks/use-toast";

interface ActionDockProps {
  onHome: () => void;
  onNew: () => void;
  onExport: () => void;
  sessionId?: string;
  showExport?: boolean;
}

/**
 * ActionDock — fixed bottom action bar on the result page.
 *
 * Always visible when mounted. Contains:
 *   - Home: back to landing page
 *   - New Analysis: start a fresh investigation
 *   - Export: download report as PDF (only when showExport=true)
 */
export function ActionDock({ onHome, onNew, onExport, sessionId, showExport = true }: ActionDockProps) {
  const [isExporting, setIsExporting] = React.useState(false);

  const handleExport = async () => {
    if (isExporting) return;
    if (sessionId) {
      setIsExporting(true);
      try {
        const res = await fetch(
          `${API_BASE}/api/v1/sessions/${encodeURIComponent(sessionId)}/report/pdf`,
          { credentials: "include" },
        );
        if (res.ok) {
          const blob = await res.blob();
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `forensic-report-${sessionId.slice(0, 8)}.pdf`;
          a.click();
          URL.revokeObjectURL(url);
          return;
        }
        toast.warning({
          title: "PDF export unavailable",
          description: "Downloading the report as JSON instead.",
        });
      } catch {
        toast.warning({
          title: "PDF export failed",
          description: "Network error. Downloading the report as JSON instead.",
        });
      } finally {
        setIsExporting(false);
      }
    }
    onExport();
  };

  return (
    <div className="fixed bottom-0 left-0 right-0 z-[100] pointer-events-none">
      <div className="pointer-events-auto max-w-3xl mx-auto px-4" style={{ paddingBottom: "max(env(safe-area-inset-bottom, 0px), 1rem)" }}>
        <div
          className="flex items-center gap-3 px-4 py-3 fc-surface"
        >
          {/* Home */}
          <button
            type="button"
            onClick={onHome}
            aria-label="Back to Home"
            className="fc-btn-secondary text-xs font-mono shrink-0 gap-2"
          >
            <HomeIcon className="w-3.5 h-3.5" />
            Home
          </button>

          {/* New Analysis — primary, fills space */}
          <button
            type="button"
            onClick={onNew}
            aria-label="Start New Analysis"
            className="fc-btn-primary flex-1 text-xs gap-2"
          >
            <Plus className="w-3.5 h-3.5" />
            New Analysis
          </button>

          {/* Export — only when report is ready */}
          {showExport && (
            <button
              type="button"
              onClick={handleExport}
              disabled={isExporting}
              aria-label={isExporting ? "Exporting report…" : "Export report"}
              className="fc-btn-secondary text-xs font-mono shrink-0 gap-2"
            >
              <Download className="w-3.5 h-3.5" />
              {isExporting ? "…" : "Export"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
