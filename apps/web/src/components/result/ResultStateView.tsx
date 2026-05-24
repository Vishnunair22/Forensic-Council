"use client";

import React from "react";
import { motion } from "framer-motion";
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
      title: "Establishing Link",
      desc: "Accessing secure forensic ledger...",
      color: "text-primary",
    },
    error: {
      icon: XCircle,
      title: "Ledger Desync",
      desc: message || "Something went wrong during report synthesis.",
      color: "text-danger",
    },
    empty: {
      icon: Search,
      title: "Awaiting Query",
      desc: "No active investigation session. Start a new one below.",
      color: "fc-text-muted",
    },
  };
  const c = configs[type];
  const Icon = c.icon;

  return (
    <div className="min-h-[70vh] flex flex-col items-center justify-center text-center px-6 relative">
      {/* Ambient terminal glow for errors */}
      {type === "error" && (
        <div className="absolute inset-0 bg-danger/5 [mask-image:radial-gradient(ellipse_at_center,black,transparent)] pointer-events-none animate-pulse" />
      )}

      {/* Screen reader announcement for state transitions */}
      <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
        {type === "loading" && "Loading forensic report, please wait."}
        {type === "error" && `Error: ${message || "Something went wrong during report synthesis."}`}
        {type === "empty" && "No active investigation session found. Start a new one below."}
      </div>

      <div className="relative mb-8">
        {/* Concentric rotating rings */}
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
          className={clsx("absolute -inset-4 border border-dashed rounded-full opacity-20", c.color)}
        />
        <div className={clsx(
          "w-20 h-20 rounded-2xl flex items-center justify-center backdrop-blur-md border shadow-2xl relative z-10 bg-black/50",
          type === "error" ? "border-danger/30" : "border-white/10"
        )}>
          <Icon className={clsx("w-10 h-10", c.color, type === "loading" && "animate-pulse")} aria-hidden="true" />
        </div>
      </div>

      <h2 className="text-2xl font-mono uppercase tracking-widest text-white mb-3">
        {c.title}
      </h2>

      {/* Terminal style description */}
      <div className="bg-black/40 border border-white/10 rounded-lg p-3 inline-block mb-10">
        <p className="text-sm font-mono text-white/60 tracking-wider">
          <span className="text-primary mr-2">&gt;</span>
          {c.desc}
        </p>
      </div>

      {(onNew || onHome) && (
        <div className="flex gap-4 flex-wrap justify-center">
          {onNew && (
            <button type="button" onClick={onNew} className="fc-btn-primary tracking-wide font-bold">
              New Investigation
            </button>
          )}
          {onHome && (
            <button type="button" onClick={onHome} className="fc-btn-secondary tracking-wide font-bold">
              <HomeIcon className="w-4 h-4" /> Hub
            </button>
          )}
        </div>
      )}
    </div>
  );
}
