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
      <div className="pointer-events-auto max-w-3xl mx-auto px-4 pb-4">
        <div
          className="flex items-center gap-3 px-4 py-3 rounded-2xl border border-white/[0.08] bg-[#02040A]/92 backdrop-blur-xl shadow-[0_-20px_60px_-10px_rgba(0,0,0,0.7)]"
        >
          {/* Home */}
          <button
            type="button"
            onClick={onHome}
            aria-label="Back to Home"
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-white/10 text-white/55 hover:text-white hover:border-white/25 hover:bg-white/[0.04] transition-all duration-150 text-xs font-mono font-bold tracking-[0.12em] uppercase shrink-0"
          >
            <HomeIcon className="w-3.5 h-3.5" />
            Home
          </button>

          {/* New Analysis — primary, fills space */}
          <button
            type="button"
            onClick={onNew}
            aria-label="Start New Analysis"
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-[var(--color-primary)] text-white hover:brightness-110 active:scale-[0.98] transition-all duration-150 text-xs font-bold tracking-[0.06em] uppercase"
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
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-white/10 text-white/55 hover:text-white hover:border-white/25 hover:bg-white/[0.04] disabled:opacity-40 disabled:cursor-not-allowed transition-all duration-150 text-xs font-mono font-bold tracking-[0.12em] uppercase shrink-0"
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
