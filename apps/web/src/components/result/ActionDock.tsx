"use client";

import React from "react";
import { Home as HomeIcon, Activity, Download } from "lucide-react";

interface ActionDockProps {
  onHome: () => void;
  onNew: () => void;
  onExport: () => void;
}

/**
 * ActionDock: The high-fidelity forensic result action bar.
 */
export function ActionDock({ onHome, onNew, onExport }: ActionDockProps) {
  return (
    <div className="fixed bottom-10 left-1/2 -translate-x-1/2 z-[100] animate-in slide-in-from-bottom-6 duration-1000 w-full max-w-xl px-6 pointer-events-none">
      <div className="bg-[#020203]/80 border border-white/10 rounded-full p-2 backdrop-blur-xl shadow-[0_40px_100px_rgba(0,0,0,0.8)] pointer-events-auto">
        <div className="flex items-center justify-between gap-2">

          <button
            onClick={onHome}
            className="flex-1 flex items-center justify-center gap-2 text-[10px] font-mono font-bold text-white/40 hover:text-white transition-colors"
          >
            <HomeIcon className="w-3.5 h-3.5" />
            HOME
          </button>

          <div className="w-[1px] h-6 bg-white/5" />

          <button
            onClick={onNew}
            className="flex-[2] btn-horizon-primary py-3 px-6 text-xs flex items-center justify-center gap-2"
          >
            <Activity className="w-3.5 h-3.5" />
            NEW ANALYSIS
          </button>

          <div className="w-[1px] h-6 bg-white/5" />

          <button
            onClick={onExport}
            className="flex-1 flex items-center justify-center gap-2 text-[10px] font-mono font-bold text-white/40 hover:text-primary transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            EXPORT
          </button>

        </div>
      </div>
    </div>
  );
}
