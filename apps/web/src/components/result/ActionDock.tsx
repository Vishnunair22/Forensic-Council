"use client";

import React from "react";
import { Home as HomeIcon, Activity, Download } from "lucide-react";

interface ActionDockProps {
  onHome: () => void;
  onNew: () => void;
  onExport: () => void;
}

export function ActionDock({ onHome, onNew, onExport }: ActionDockProps) {
  return (
    <div className="fixed bottom-10 left-1/2 -translate-x-1/2 z-[100] animate-in slide-in-from-bottom-6 duration-1000">
      <div className="flex items-center gap-2 p-1.5 rounded-full bg-black/60 backdrop-blur-2xl border border-white/10 shadow-[0_20px_50px_rgba(0,0,0,0.8)]">
        <button
          onClick={onHome}
          className="btn-secondary border-none hover:border-none shadow-none text-[11px] font-bold px-6 py-2.5 h-auto min-h-0 text-white/40 hover:text-white"
        >
          <HomeIcon className="w-3.5 h-3.5" /> Home
        </button>

        <div className="w-[1px] h-6 bg-white/5" />

        <button
          onClick={onNew}
          className="btn-primary text-[11px] px-8 py-2.5 h-auto min-h-0 shadow-xl shadow-cyan-900/40"
        >
          <Activity className="w-3.5 h-3.5" /> New Investigation
        </button>

        <div className="w-[1px] h-6 bg-white/5" />

        <button
          onClick={onExport}
          className="btn-secondary border-none hover:border-none shadow-none text-[11px] font-bold px-6 py-2.5 h-auto min-h-0 text-white/40 hover:text-cyan-400"
        >
          <Download className="w-3.5 h-3.5" /> Export
        </button>
      </div>
    </div>
  );
}
