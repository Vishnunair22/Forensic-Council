"use client";

import React, { useEffect, useState } from "react";
import { X, History, Trash2, ShieldCheck, FileText, AlertTriangle, AlertCircle, CheckCircle } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import clsx from "clsx";
import { useRouter } from "next/navigation";

export interface HistoryItem {
  sessionId: string;
  fileName: string;
  verdict: string;
  timestamp: number;
  type: "Initial" | "Deep";
}

export function HistoryDrawer() {
  const router = useRouter();
  const [isOpen, setIsOpen] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);

  const loadHistory = () => {
    try {
      const stored = localStorage.getItem("forensic_history");
      if (stored) {
        setHistory(JSON.parse(stored));
      }
    } catch (e) {
      console.error("Failed to parse history", e);
    }
  };

  useEffect(() => {
    loadHistory();
    // Re-load history if it opens
  }, [isOpen]);

  const removeHistoryItem = (sessionId: string) => {
    const updated = history.filter(h => h.sessionId !== sessionId);
    setHistory(updated);
    localStorage.setItem("forensic_history", JSON.stringify(updated));
  };

  const clearAllHistory = () => {
    setHistory([]);
    localStorage.setItem("forensic_history", JSON.stringify([]));
  };

  // Verdict config to match result page icons
  const getVerdictUi = (v: string) => {
    const u = (v || "").toUpperCase();
    if (u === "AUTHENTIC" || u === "CERTAIN") return { color: "text-emerald-400", dot: "bg-emerald-400", Icon: CheckCircle };
    if (u === "MANIPULATED" || u === "MANIPULATION DETECTED" || u === "LIKELY_MANIPULATED") return { color: "text-red-400", dot: "bg-red-400", Icon: AlertTriangle };
    if (u === "INCONCLUSIVE") return { color: "text-amber-400", dot: "bg-amber-400", Icon: AlertCircle };
    return { color: "text-amber-400", dot: "bg-amber-400", Icon: AlertTriangle };
  };

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="fixed top-1/2 right-0 -translate-y-1/2 translate-x-[2px] transition-transform hover:translate-x-0 z-40 bg-surface-high border border-border-bold border-r-0 rounded-l-2xl p-3 shadow-xl group"
        aria-label="Open History"
      >
        <span className="flex flex-col items-center gap-2">
           <History className="w-5 h-5 text-indigo-400 group-hover:text-indigo-300" />
           <span className="[writing-mode:vertical-lr] rotate-180 text-[10px] font-bold tracking-[0.2em] text-foreground/40 uppercase group-hover:text-foreground/60 mt-2">History</span>
        </span>
      </button>

      <AnimatePresence>
        {isOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              onClick={() => setIsOpen(false)}
              className="fixed inset-0 bg-background/60 backdrop-blur-sm z-50"
            />
            <motion.div
              initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
              transition={{ type: "spring", damping: 25, stiffness: 200 }}
              className="fixed inset-y-0 right-0 w-80 max-w-[85vw] bg-surface-low border-l border-border-subtle z-50 flex flex-col shadow-2xl"
            >
              <div className="flex items-center justify-between p-5 border-b border-border-subtle bg-surface-mid">
                <h2 className="text-[11px] font-bold tracking-widest uppercase text-foreground/60 flex items-center gap-2">
                  <History className="w-4 h-4 text-indigo-400" /> Analysis History
                </h2>
                <button onClick={() => setIsOpen(false)} className="p-1 rounded-md hover:bg-surface-high text-foreground/40 transition-colors">
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-4 space-y-3">
                {history.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full text-foreground/20">
                    <History className="w-10 h-10 mb-3" />
                    <p className="text-[10px] uppercase tracking-widest font-mono font-bold">No History Found</p>
                  </div>
                ) : (
                  history.map((item) => {
                    const ui = getVerdictUi(item.verdict);
                    const UIcon = ui.Icon;
                    return (
                      <div key={item.sessionId} className="relative group bg-surface-mid border border-border-subtle rounded-xl p-4 hover:border-indigo-500/30 transition-colors overflow-hidden shadow-sm">
                        <div className="flex justify-between items-start mb-3 pr-6">
                           <div className="flex items-center gap-2 overflow-hidden">
                              <FileText className="w-3.5 h-3.5 text-foreground/20 shrink-0" />
                              <span className="text-xs font-bold text-foreground/80 truncate" title={item.fileName}>{item.fileName}</span>
                           </div>
                        </div>

                        <div className="space-y-2">
                           <div className="flex items-center gap-2">
                              <UIcon className={clsx("w-3.5 h-3.5 shrink-0", ui.color)} />
                              <span className={clsx("text-[11px] font-bold uppercase tracking-wide", ui.color)}>
                                {item.verdict.replace(/_/g, " ")}
                              </span>
                           </div>
                           <div className="flex justify-between items-center text-[10px] text-foreground/40 font-mono font-bold">
                              <span className="px-1.5 py-0.5 rounded border border-border-subtle bg-surface-high uppercase text-[9px]">{item.type}</span>
                              <span className="font-medium">{new Date(item.timestamp).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</span>
                           </div>
                        </div>

                        {/* Inline delete individual element */}
                        <button
                          onClick={() => removeHistoryItem(item.sessionId)}
                          className="absolute top-3 right-3 p-1.5 rounded-md hover:bg-rose-500/10 text-foreground/20 hover:text-rose-500 transition-all opacity-0 group-hover:opacity-100"
                          title="Clear Item"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </div>
                    );
                  })
                )}
              </div>

              {history.length > 0 && (
                <div className="p-4 border-t border-border-subtle bg-surface-mid">
                  <button
                    onClick={clearAllHistory}
                    className="w-full py-2.5 rounded-lg border border-rose-500/20 bg-rose-500/5 text-rose-500 hover:bg-rose-500/10 text-[10px] font-bold uppercase tracking-widest transition-colors flex items-center justify-center gap-2"
                  >
                    <Trash2 className="w-4 h-4" /> Clear All History
                  </button>
                </div>
              )}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
