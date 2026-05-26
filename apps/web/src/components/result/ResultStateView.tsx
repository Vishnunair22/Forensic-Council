"use client";

import React from "react";
import clsx from "clsx";
import { Activity, XCircle, Search, Home as HomeIcon } from "lucide-react";

interface ResultStateViewProps {
  type: "loading" | "error" | "empty";
  message?: string;
  onNew?: () => void;
  onHome?: () => void;
}

export function ResultStateView({ type, message, onNew, onHome }: ResultStateViewProps) {
  const configs = {
    loading: {
      icon: Activity,
      title: "Loading Report",
      desc: "Accessing secure forensic ledger...",
      color: "text-primary",
    },
    error: {
      icon: XCircle,
      title: "Report Unavailable",
      desc: message || "Something went wrong during report synthesis.",
      color: "text-danger",
    },
    empty: {
      icon: Search,
      title: "No Active Session",
      desc: "No investigation session found. Start a new one below.",
      color: "fc-text-muted",
    },
  };
  const c = configs[type];
  const Icon = c.icon;

  return (
    <div className="min-h-[70vh] flex flex-col items-center justify-center text-center px-6 relative">
      {/* Screen reader announcement for state transitions */}
      <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
        {type === "loading" && "Loading forensic report, please wait."}
        {type === "error" && `Error: ${message || "Something went wrong during report synthesis."}`}
        {type === "empty" && "No active investigation session found. Start a new one below."}
      </div>

      <div className="relative mb-8">
        <div className={clsx(
          "w-20 h-20 rounded-2xl flex items-center justify-center border relative z-10 fc-surface-quiet",
          type === "error" ? "border-danger/30" : "border-white/10"
        )}>
          <Icon className={clsx("w-10 h-10", c.color, type === "loading" && "animate-pulse")} aria-hidden="true" />
        </div>
      </div>

      <h2 className="text-2xl font-heading font-bold fc-text-primary mb-3">
        {c.title}
      </h2>

      <div className="fc-surface-quiet rounded-xl px-4 py-3 inline-block mb-10">
        <p className="text-sm fc-text-secondary">{c.desc}</p>
      </div>

      {(onNew || onHome) && (
        <div className="flex gap-4 flex-wrap justify-center">
          {onNew && (
            <button type="button" onClick={onNew} className="fc-btn-primary">
              New Investigation
            </button>
          )}
          {onHome && (
            <button type="button" onClick={onHome} className="fc-btn-secondary flex items-center gap-2">
              <HomeIcon className="w-4 h-4" /> Hub
            </button>
          )}
        </div>
      )}
    </div>
  );
}
