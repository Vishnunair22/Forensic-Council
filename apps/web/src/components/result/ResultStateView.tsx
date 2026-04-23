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
      title: "Analysis Error",
      desc: message || "Something went wrong during report synthesis.",
      color: "text-danger",
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
      <div className="w-24 h-24 rounded-[2.5rem] premium-glass border-border-subtle flex items-center justify-center mb-10 shadow-2xl transition-transform hover:scale-110 duration-500">
        <Icon
          className={clsx("w-12 h-12", c.color, type === "loading" && "animate-pulse")}
          aria-hidden="true"
        />
      </div>
      <h2 className="text-4xl font-black text-white tracking-tighter mb-4">
        {c.title}
      </h2>
      <p className="text-base font-medium text-white/50 max-w-sm mb-12 tracking-wide leading-relaxed">{c.desc}</p>

      {(onNew || onHome) && (
        <div className="flex gap-4 flex-wrap justify-center">
          {onNew && (
            <button onClick={onNew} className="btn-premium px-10 py-4 tracking-wide font-bold !normal-case">
              New Investigation
            </button>
          )}
          {onHome && (
            <button onClick={onHome} className="btn-outline px-10 py-4 tracking-wide font-bold !normal-case">
              <HomeIcon className="w-4 h-4" /> Hub
            </button>
          )}
        </div>
      )}
    </div>
  );
}
