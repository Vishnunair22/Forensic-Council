"use client";

import React from "react";
import { Home, Plus } from "lucide-react";

interface PageNavigationProps {
  onHome: () => void;
  onNew: () => void;
}

export function PageNavigation({ onHome, onNew }: PageNavigationProps) {
  return (
    <div className="flex gap-3">
      <button
        type="button"
        onClick={onNew}
        className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl border border-primary/30 bg-primary/5 text-sm font-bold text-primary hover:bg-primary/10 hover:border-primary/50 transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
      >
        <Plus className="w-4 h-4" />
        New Analysis
      </button>
      <button
        type="button"
        onClick={onHome}
        className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl border border-white/[0.08] bg-transparent text-sm font-bold fc-text-muted hover:text-white hover:border-white/[0.15] hover:bg-white/[0.04] transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/20"
      >
        <Home className="w-4 h-4" />
        Back to Home
      </button>
    </div>
  );
}
