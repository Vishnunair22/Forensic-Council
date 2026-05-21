"use client";

import React from "react";
import {
  History as HistoryIcon,
  X,
  ArrowRight
} from "lucide-react";
import clsx from "clsx";
import { type HistoryItem } from "@/lib/types";
import { EvidenceThumbnail } from "./EvidenceThumbnail";
import { useSessionStorage } from "@/hooks/useSessionStorage";
import { motion, useReducedMotion } from "framer-motion";

interface HistoryPanelProps {
  onDismiss: () => void;
  onSelect: (sessionId: string) => void;
}

export function HistoryPanel({ onDismiss, onSelect }: HistoryPanelProps) {
  const [history, setHistory] = useSessionStorage<HistoryItem[]>("forensic_history", [], true);
  const shouldReduceMotion = useReducedMotion();

  const removeItem = (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    setHistory((prev) => prev.filter((h) => h.sessionId !== sessionId));
  };

  const [showConfirm, setShowConfirm] = React.useState(false);

  const clearAll = () => {
    setHistory([]);
    setShowConfirm(false);
  };

  const getVerdictStyle = (verdict: string) => {
    const v = (verdict || "").toUpperCase();
    if (v.includes("MANIPULATED")) return "text-danger bg-danger/10 border-danger/30";
    if (v.includes("SUSPICIOUS")) return "text-warning bg-warning/10 border-warning/30";
    if (v.includes("AUTHENTIC")) return "text-success bg-success/10 border-success/30";
    return "fc-text-faint bg-white/5 border-white/10";
  };

  return (
    <div className="w-full max-w-5xl mx-auto pb-32">
      <div className="bg-transparent border border-white/5 rounded-2xl shadow-xl overflow-hidden">
        <div className="bg-transparent">

          {/* --- Header --- */}
          <div className="flex flex-col md:flex-row items-center justify-between px-10 py-10 border-b border-white/5 gap-6">
            <div className="flex flex-col gap-2">
               <h3 className="text-3xl font-heading font-bold text-white flex items-center gap-4">
                 <HistoryIcon className="w-6 h-6 text-primary" />
                 Investigation Archive
               </h3>
               <p className="fc-eyebrow fc-text-faint">
                 Forensic Registry // Secure Storage V2
               </p>
            </div>

            <div className="flex items-center gap-6">
              {history.length > 0 && (
                <>
                  {showConfirm ? (
                    <div className="flex items-center gap-3 bg-danger/10 p-2 rounded-xl border border-danger/20">
                      <span className="text-xs font-mono text-danger font-bold tracking-wider px-2">Confirm?</span>
                      <button
                        type="button"
                        onClick={clearAll}
                        className="py-1 px-3 text-xs font-mono font-bold text-[#05070D] bg-danger rounded-md"
                      >
                        Yes
                      </button>
                      <button
                        type="button"
                        onClick={() => setShowConfirm(false)}
                        className="py-1 px-3 text-xs font-mono font-bold fc-text-secondary bg-white/5 rounded-md"
                      >
                        No
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setShowConfirm(true)}
                      className="fc-btn-secondary py-2 px-4 text-xs text-danger border-danger/20 hover:bg-danger/5"
                    >
                      Clear Archive
                    </button>
                  )}
                </>
              )}
              <button
                type="button"
                onClick={onDismiss}
                className="fc-eyebrow fc-text-muted hover:text-primary-accent transition-colors"
              >
                Back To Analysis
              </button>
            </div>
          </div>

          {/* --- List --- */}
          <div className="p-10">
            {history.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-32 gap-6">
                <div className="relative w-24 h-24 flex items-center justify-center">
                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{ duration: 15, repeat: Infinity, ease: "linear" }}
                    className="absolute inset-0 rounded-full border border-white/5 border-dashed"
                  />
                  <HistoryIcon className="w-10 h-10 text-white/5" />
                </div>
                <div className="text-center">
                  <p className="text-sm font-heading font-bold fc-text-faint mb-2 tracking-widest">Archive Empty</p>
                  <p className="text-xs font-mono fc-text-faint max-w-xs leading-relaxed">
                    System awaiting initial analysis payloads for registry sync.
                  </p>
                </div>
              </div>
) : (
              <div className="grid gap-6" role="list" aria-label="Investigation archive">
                {[...history].sort((a,b) => b.timestamp - a.timestamp).map((item, i) => (
                  <motion.div
                    key={item.sessionId}
                    initial={shouldReduceMotion ? {} : { opacity: 0, x: -20 }}
                    animate={shouldReduceMotion ? {} : { opacity: 1, x: 0 }}
                    transition={shouldReduceMotion ? { duration: 0 } : { delay: i * 0.05 }}
                    className="group relative p-6 cursor-pointer transition-colors duration-200 border-t border-white/5 first:border-t-0 bg-transparent hover:bg-white/[0.02]"
                  >
                    <article aria-label={`View analysis for ${item.fileName}`}>
                      <div className="flex flex-col md:flex-row gap-6 items-center">
                        <div aria-hidden="true" className="relative w-16 h-16 shrink-0 flex items-center justify-center">
                          <motion.div
                            animate={shouldReduceMotion ? {} : { rotate: 360 }}
                            transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
                            className="absolute inset-0 rounded-full border border-primary/10 border-dashed"
                          />
                          <div className="w-12 h-12 rounded-lg overflow-hidden border border-white/5">
                            <EvidenceThumbnail
                              thumbnail={item.thumbnail}
                              mimeType={item.mime}
                              fileName={item.fileName}
                              className="w-full h-full object-cover"
                            />
                          </div>
                        </div>

                        <div className="flex-1 min-w-0">
                           <div className="flex items-center gap-3 mb-2">
                              <span className="fc-eyebrow fc-text-primary-accent">Session {item.sessionId.slice(-6)}</span>
                              <span className="text-xs font-mono fc-text-faint">[{item.type} Analysis]</span>
                           </div>
                           <h4 className="text-lg font-heading font-bold text-white/80 truncate group-hover:text-white transition-colors">
                             {item.fileName}
                           </h4>
                        </div>

                        <div className={clsx(
                          "px-4 py-1.5 rounded border fc-eyebrow",
                          getVerdictStyle(item.verdict)
                        )}>
                          {item.verdict?.replace(/_/g, " ")}
                        </div>

                        <div className="flex items-center gap-4">
                          <div className="text-right hidden lg:block">
                             <div className="text-xs font-mono fc-text-faint">Timestamp</div>
                             <div className="text-xs font-mono fc-text-muted">
                               {new Date(item.timestamp).toLocaleDateString()} {new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                             </div>
                          </div>
                          <button
                            type="button"
                            onClick={(e) => removeItem(e, item.sessionId)}
                            aria-label={`Remove ${item.fileName} from archive`}
                            className="relative z-10 p-3 rounded-lg border border-white/5 text-white/20 hover:text-danger hover:border-danger/30 transition-all"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    </article>

                    <button
                      type="button"
                      onClick={() => onSelect(item.sessionId)}
                      aria-label={`View analysis for ${item.fileName}`}
                      className="absolute inset-0 rounded-2xl"
                      style={{ zIndex: 1 }}
                    />

                    <div aria-hidden="true" className="absolute top-0 right-0 p-1 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
                       <ArrowRight className="w-3 h-3 text-primary" />
                    </div>
                  </motion.div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
