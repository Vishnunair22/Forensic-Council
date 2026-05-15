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
      <div className="pointer-events-auto bg-[#06090E] border-t border-[#333333] px-6 py-4 flex items-center justify-between max-w-5xl mx-auto gap-4">
          <button
            type="button"
            onClick={onHome}
            className="flex items-center justify-center gap-2 px-6 py-3 text-xs font-bold tracking-widest uppercase transition-colors text-white/60 hover:text-white hover:bg-[#111111] border border-[#333333]"
          >
            <HomeIcon className="w-3.5 h-3.5" />
            Home
          </button>

          <button
            type="button"
            onClick={onNew}
            className="flex-1 px-8 py-3 text-sm font-bold tracking-widest uppercase flex items-center justify-center gap-2 transition-colors bg-white text-black hover:bg-gray-200"
          >
            <Activity className="w-3.5 h-3.5" />
            New Analysis
          </button>

          <button
            type="button"
            onClick={handleExport}
            disabled={isExporting}
            className="flex items-center justify-center gap-2 px-6 py-3 text-xs font-bold tracking-widest uppercase transition-colors text-white/60 hover:text-white hover:bg-[#111111] border border-[#333333] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Download className="w-3.5 h-3.5" />
            {isExporting ? "Exporting" : "Export"}
          </button>
      </div>
    </div>
  );
}
