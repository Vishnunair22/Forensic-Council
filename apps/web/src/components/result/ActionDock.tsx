"use client";

import React from "react";
import { Home as HomeIcon, Activity, Download } from "lucide-react";
import { API_BASE } from "@/lib/api";
import { toast } from "@/hooks/use-toast";

interface ActionDockProps {
  onHome: () => void;
  onNew: () => void;
  onExport: () => void;
  sessionId?: string;
}

/**
 * ActionDock: The high-fidelity forensic result action bar.
 */
export function ActionDock({ onHome, onNew, onExport, sessionId }: ActionDockProps) {
  const [isExporting, setIsExporting] = React.useState(false);
  const handleExport = async () => {
    if (isExporting) return;
    if (sessionId) {
      setIsExporting(true);
      try {
        const res = await fetch(`${API_BASE}/api/v1/sessions/${encodeURIComponent(sessionId)}/report/pdf`, {
          credentials: "include",
        });
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
        // Non-OK response: surface a hint, then fall through to JSON fallback.
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
    <div className="fixed bottom-0 left-0 right-0 z-[100] animate-in slide-in-from-bottom-6 duration-700 w-full pointer-events-none">
      <div className="pointer-events-auto bg-[#02040A]/90 backdrop-blur-xl border-t border-x border-white/10 px-6 py-4 flex items-center justify-between max-w-5xl mx-auto gap-4 rounded-t-xl shadow-[0_-40px_80px_-20px_rgba(0,0,0,0.8)]">
          <button
            type="button"
            onClick={onHome}
            className="btn-outline flex-none !py-3"
          >
            <HomeIcon className="w-4 h-4" />
            Hub
          </button>

          <button
            type="button"
            onClick={onNew}
            className="btn-primary flex-1 !py-3"
          >
            <Activity className="w-4 h-4" />
            New Analysis
          </button>

          <button
            type="button"
            onClick={handleExport}
            disabled={isExporting}
            className="btn-outline flex-none !py-3 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Download className="w-4 h-4" />
            {isExporting ? "Exporting" : "Export"}
          </button>
      </div>
    </div>
  );
}
