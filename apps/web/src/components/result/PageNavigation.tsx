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
        className="flex-1 fc-btn-primary"
      >
        <Plus className="w-4 h-4" aria-hidden="true" />
        New Analysis
      </button>
      <button
        type="button"
        onClick={onHome}
        className="flex-1 fc-btn-secondary"
      >
        <Home className="w-4 h-4" aria-hidden="true" />
        Back to Home
      </button>
    </div>
  );
}
