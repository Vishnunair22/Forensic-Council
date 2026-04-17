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
      color: "text-cyan-400",
    },
    error: {
      icon: XCircle,
      title: "Analysis Error",
      desc: message || "Something went wrong during report synthesis.",
      color: "text-rose-500",
    },
    empty: {
      icon: Search,
      title: "No Results Found",
      desc: "No active investigation session. Start a new one below.",
      color: "text-white/20",
    },
  };
  const c = configs[type];
  const Icon = c.icon;

  return (
    <div className="min-h-[70vh] flex flex-col items-center justify-center text-center px-6">
      <div className="w-20 h-20 rounded-[2rem] bg-white/[0.02] border border-white/5 flex items-center justify-center mb-8">
        <Icon
          className={clsx("w-10 h-10", c.color, type === "loading" && "animate-pulse")}
          aria-hidden="true"
        />
      </div>
      <h2 className="text-3xl font-bold text-white tracking-tight mb-3 font-heading">
        {c.title}
      </h2>
      <p className="text-sm font-medium text-white/50 max-w-sm mb-10">{c.desc}</p>

      {(onNew || onHome) && (
        <div className="flex gap-4 flex-wrap justify-center">
          {onNew && (
            <button onClick={onNew} className="btn-pill-primary px-8">
              New Investigation
            </button>
          )}
          {onHome && (
            <button onClick={onHome} className="btn-pill-secondary px-8">
              <HomeIcon className="w-4 h-4" /> Home
            </button>
          )}
        </div>
      )}
    </div>
  );
}
