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
      <div className="flex items-center gap-2 p-2 rounded-full premium-glass border-border-subtle shadow-[0_20px_50px_rgba(0,0,0,0.8)]">
        <button
          onClick={onHome}
          className="btn-outline border-none shadow-none text-[10px] font-black px-6 py-2.5 h-auto min-h-0 tracking-widest"
        >
          <HomeIcon className="w-3.5 h-3.5" /> Back to Home
        </button>

        <div className="w-[1px] h-6 bg-white/5" />

        <button
          onClick={onNew}
          className="btn-premium text-[10px] px-8 py-2.5 h-auto min-h-0 tracking-widest"
        >
          <Activity className="w-3.5 h-3.5" /> New Analysis
        </button>

        <div className="w-[1px] h-6 bg-white/5" />

        <button
          onClick={onExport}
          className="btn-outline border-none shadow-none text-[10px] font-black px-6 py-2.5 h-auto min-h-0 tracking-widest"
        >
          <Download className="w-3.5 h-3.5" /> Export
        </button>
      </div>
    </div>
  );
}
