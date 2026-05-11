"use client";

import React from "react";
import { Home as HomeIcon, Activity, Download } from "lucide-react";

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
    // Try PDF download from API if sessionId available; else call parent onExport
    if (sessionId) {
      try {
        const token = typeof document !== "undefined"
          ? document.cookie.split("; ").find(r => r.startsWith("access_token="))?.split("=")[1]
          : undefined;
        const res = await fetch(`/api/v1/sessions/${sessionId}/report/pdf`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
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
    <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-[100] animate-in slide-in-from-bottom-6 duration-700 w-full max-w-lg px-5 pointer-events-none">
      <div
        className="rounded-full p-1.5 pointer-events-auto"
        style={{
          background: "rgba(5,9,18,0.92)",
          border: "1px solid rgba(165,200,255,0.09)",
          backdropFilter: "blur(24px)",
          WebkitBackdropFilter: "blur(24px)",
          boxShadow: "0 32px 80px rgba(0,0,0,0.75), 0 0 0 1px rgba(79,142,247,0.05), inset 0 1px 0 rgba(255,255,255,0.04)",
        }}
      >
        <div className="flex items-center justify-between gap-1.5">
          <button
            onClick={onHome}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-full text-[10px] font-mono font-bold uppercase tracking-[0.18em] transition-all duration-200"
            style={{ color: "rgba(255,255,255,0.35)" }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.color = "rgba(255,255,255,0.75)";
              (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.04)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.color = "rgba(255,255,255,0.35)";
              (e.currentTarget as HTMLElement).style.background = "";
            }}
          >
            <HomeIcon className="w-3.5 h-3.5" />
            Home
          </button>

          <button
            onClick={onNew}
            className="flex-[2] btn-horizon-primary py-2.5 px-6 text-[11px] flex items-center justify-center gap-2"
          >
            <Activity className="w-3.5 h-3.5" />
            New Analysis
          </button>

          <button
            onClick={handleExport}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-full text-[10px] font-mono font-bold uppercase tracking-[0.18em] transition-all duration-200"
            style={{ color: "rgba(255,255,255,0.35)" }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.color = "var(--color-primary)";
              (e.currentTarget as HTMLElement).style.background = "rgba(79,142,247,0.06)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.color = "rgba(255,255,255,0.35)";
              (e.currentTarget as HTMLElement).style.background = "";
            }}
          >
            <Download className="w-3.5 h-3.5" />
            Export
          </button>
        </div>
      </div>
    </div>
  );
}
