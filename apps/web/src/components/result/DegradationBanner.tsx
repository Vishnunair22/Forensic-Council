"use client";

import React from "react";
import { AlertTriangle } from "lucide-react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { AGENTS } from "@/lib/constants";

interface DegradationBannerProps {
  flags: string[];
  /** agent_id → tool names that ran in a degraded/fallback mode. */
  perAgent?: Record<string, string[]>;
}

const _AGENT_NAME: Record<string, string> = Object.fromEntries(
  AGENTS.map((a) => [a.id, a.name]),
);

function _humanizeTool(tool: string): string {
  return tool.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function DegradationBanner({ flags, perAgent }: DegradationBannerProps) {
  const prefersReduced = useReducedMotion();
  const safeFlags = flags ?? [];
  const agentEntries = Object.entries(perAgent ?? {}).filter(
    ([, tools]) => Array.isArray(tools) && tools.length > 0,
  );
  if (safeFlags.length === 0 && agentEntries.length === 0) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={prefersReduced ? false : { opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.16, ease: "easeOut" }}
        className="border border-warning/20 rounded-2xl overflow-hidden fc-surface-quiet"
      >
        <div className="px-5 py-3.5 border-b border-warning/10 flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5 text-warning shrink-0" aria-hidden="true" />
          <span className="fc-eyebrow text-warning">
            Analysis Degradation Notice
          </span>
          {safeFlags.length > 0 && (
            <span className="fc-eyebrow text-warning/60 ml-auto">
              {safeFlags.length} flag{safeFlags.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>
        <div className="px-5 py-4 space-y-2.5">
          {safeFlags.map((flag, i) => (
            <div
              key={`flag-${i}`}
              className="flex items-start gap-2.5 text-xs leading-relaxed"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-warning/60 mt-1.5 shrink-0" aria-hidden="true" />
              <span className="fc-text-muted">{flag}</span>
            </div>
          ))}
          {agentEntries.length > 0 && (
            <div className="pt-1 space-y-1.5">
              {agentEntries.map(([agentId, tools]) => (
                <div key={`deg-${agentId}`} className="text-xs leading-relaxed">
                  <span className="fc-text-secondary font-semibold">
                    {_AGENT_NAME[agentId] ?? agentId}:
                  </span>{" "}
                  <span className="fc-text-muted">
                    {tools.map(_humanizeTool).join(", ")} ran in fallback mode
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
