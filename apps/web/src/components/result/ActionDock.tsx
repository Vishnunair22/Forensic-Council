"use client";

import React from "react";
import { Home as HomeIcon, Activity, Download } from "lucide-react";
import { API_BASE } from "@/lib/api";

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
  const handleExport = async () => {
    if (sessionId) {
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
      } catch {
        // Fall through to parent handler
      }
    }
    onExport();
  };
  return (
    <div className="fixed bottom-4 sm:bottom-8 left-1/2 -translate-x-1/2 z-[100] animate-in slide-in-from-bottom-6 duration-700 w-full max-w-lg px-3 sm:px-5 pointer-events-none">
      <div className="rounded-full p-1.5 pointer-events-auto fc-surface-crisp backdrop-blur-[24px]">

        <div className="flex items-center justify-between gap-1.5">
          <button
            type="button"
            onClick={onHome}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-full text-[10px] font-mono font-bold uppercase tracking-[0.18em] fc-transition fc-focus-ring text-white/35 hover:text-white/75 hover:bg-white/5"
          >
            <HomeIcon className="w-3.5 h-3.5" />
            Home
          </button>

          <button
            type="button"
            onClick={onNew}
            className="flex-[2] btn-horizon-primary py-2.5 px-6 text-[11px] flex items-center justify-center gap-2"
          >
            <Activity className="w-3.5 h-3.5" />
            New Analysis
          </button>

          <button
            type="button"
            onClick={handleExport}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-full text-[10px] font-mono font-bold uppercase tracking-[0.18em] fc-transition fc-focus-ring text-white/35 hover:text-primary hover:bg-primary/5"
          >
            <Download className="w-3.5 h-3.5" />
            Export
          </button>
        </div>
      </div>
    </div>
  );
}
