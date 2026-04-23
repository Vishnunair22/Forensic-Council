"use client";

import React from "react";
import { 
  History as HistoryIcon, 
  Trash2, 
  X, 
  ArrowRight, 
  Clock,
  ShieldCheck,
  Calendar
} from "lucide-react";
import clsx from "clsx";
import { type HistoryItem } from "@/lib/types";
import { EvidenceThumbnail } from "./EvidenceThumbnail";
import { useSessionStorage } from "@/hooks/useSessionStorage";

interface HistoryPanelProps {
  onDismiss: () => void;
  onSelect: (sessionId: string) => void;
}

export function HistoryPanel({ onDismiss, onSelect }: HistoryPanelProps) {
  const [history, setHistory] = useSessionStorage<HistoryItem[]>("forensic_history", [], true);

  const removeItem = (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    setHistory((prev) => prev.filter((h) => h.sessionId !== sessionId));
  };

  const clearAll = () => {
    if (!window.confirm("Are you sure you want to clear all investigation history?")) return;
    setHistory([]);
  };

  const getVerdictStyle = (verdict: string) => {
    const v = (verdict || "").toUpperCase();
    if (v.includes("MANIPULATED")) return "text-rose-400 bg-rose-500/5 border-rose-500/10";
    if (v.includes("SUSPICIOUS")) return "text-amber-400 bg-amber-500/5 border-amber-500/10";
    if (v.includes("AUTHENTIC")) return "text-emerald-400 bg-emerald-500/5 border-emerald-500/10";
    return "text-white/40 bg-white/5 border-white/10";
  };

  return (
    <div className="w-full max-w-4xl mx-auto animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="glass-panel rounded-[2.5rem] border border-white/5 bg-white/[0.01] overflow-hidden shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-10 py-8 border-b border-white/5">
          <div className="flex flex-col gap-1">
             <h3 className="text-xl font-bold text-white flex items-center gap-3">
               <HistoryIcon className="w-5 h-5 text-primary/50" />
               Investigation Archive
             </h3>
             <p className="text-[11px] font-medium text-white/20 ml-8 tracking-wide">Historical Forensic Records and Session Logs</p>
          </div>
          
          <div className="flex items-center gap-6">
            {history.length > 0 && (
              <button
                onClick={clearAll}
                className="group flex items-center gap-2 px-4 py-2 rounded-full text-xs font-semibold text-rose-500/50 hover:text-rose-400 hover:bg-rose-500/10 transition-all outline-none"
              >
                <Trash2 className="w-3.5 h-3.5" /> Clear All
              </button>
            )}
            <button 
              onClick={onDismiss} 
              className="text-xs font-semibold tracking-wide text-white/50 hover:text-primary transition-colors"
            >
              Back to Analysis
            </button>
          </div>
        </div>

        {/* List */}
        <div className="p-8">
          {history.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24 gap-6 text-white/10">
              <div className="w-24 h-24 rounded-[2rem] bg-white/[0.02] border border-white/5 flex items-center justify-center">
                <HistoryIcon className="w-10 h-10 opacity-20" />
              </div>
              <div className="text-center">
                <p className="text-base font-bold tracking-wide mb-2 text-white/80">Archive Empty</p>
                <p className="text-xs text-white/50 max-w-xs">Completed forensic analyses will appear here. Upload evidence to begin your first investigation.</p>
              </div>
            </div>
          ) : (
            <div className="grid gap-6">
              {history.sort((a,b) => b.timestamp - a.timestamp).map((item) => (
                <div
                  key={item.sessionId}
                  onClick={() => onSelect(item.sessionId)}
                  className="group relative flex flex-col gap-5 p-6 rounded-[2rem] bg-white/[0.01] border border-white/5 hover:border-white/10 hover:bg-white/[0.02] transition-all cursor-pointer"
                >
                  {/* Top Row: Visual + Title + Actions */}
                  <div className="flex items-center gap-5">
                    <div className="w-16 h-16 shrink-0 rounded-2xl overflow-hidden border border-white/5 shadow-xl">
                      <EvidenceThumbnail
                        thumbnail={item.thumbnail}
                        mimeType={item.mime}
                        fileName={item.fileName}
                        className="w-full h-full object-cover"
                      />
                    </div>
                    
                    <div className="flex-1 min-w-0 pr-24">
                       <h4 className="text-lg font-bold text-white/80 break-words leading-tight group-hover:text-white transition-colors">
                         {item.fileName}
                       </h4>
                    </div>

                    <div className="absolute top-6 right-8 flex items-center gap-3">
                      <button
                        onClick={(e) => removeItem(e, item.sessionId)}
                        className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 text-white/20 hover:text-rose-400 hover:bg-rose-500/10 hover:border-rose-500/20 transition-all"
                        aria-label="Remove from history"
                      >
                        <X className="w-4 h-4" />
                      </button>
                      <div className="p-2.5 rounded-xl bg-primary/10 border border-primary/20 text-primary group-hover:scale-110 transition-transform">
                        <ArrowRight className="w-4 h-4" />
                      </div>
                    </div>
                  </div>

                  {/* Bottom Row: Metadata Ribbon */}
                  <div className="flex flex-wrap items-center gap-x-8 gap-y-3 pt-5 border-t border-white/[0.03]">
                    <div className={clsx(
                      "flex items-center gap-2 px-3 py-1 rounded-full border text-[10px] font-bold tracking-wide",
                      getVerdictStyle(item.verdict)
                    )}>
                      <ShieldCheck className="w-3.5 h-3.5" />
                      {(item.verdict ?? "Unknown").replace(/_/g, " ").replace(/\w\S*/g, (w) => (w.replace(/^\w/, (c) => c.toUpperCase())))}
                    </div>

                    <div className="flex items-center gap-2 text-white/50 text-[11px] font-medium">
                      <Clock className="w-3.5 h-3.5 text-white/10" />
                      <span>{item.analysisTime || "Duration N/A"}</span>
                    </div>

                    {item.score !== undefined && (
                       <div className="flex items-center gap-2 text-white/50 text-[11px] font-medium">
                         <div className="w-1.5 h-1.5 rounded-full bg-primary/40" />
                         <span>{item.score}% Confidence</span>
                       </div>
                    )}

                    <div className="flex items-center gap-2 text-white/50 text-[11px] font-medium ml-auto">
                      <Calendar className="w-3.5 h-3.5 text-white/10" />
                      <span>
                        {new Date(item.timestamp).toLocaleString(undefined, {
                          month: "short", day: "numeric", year: "numeric",
                          hour: "numeric", minute: "2-digit",
                        })}
                      </span>
                    </div>

                    <span className="text-[11px] font-semibold tracking-wide text-white/50 px-2 py-0.5 rounded-full border border-white/5 bg-white/[0.02]">
                      {item.type} Analysis
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
