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
import { motion } from "framer-motion";

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
    if (v.includes("MANIPULATED")) return "text-danger bg-danger/10 border-danger/30";
    if (v.includes("SUSPICIOUS")) return "text-warning bg-warning/10 border-warning/30";
    if (v.includes("AUTHENTIC")) return "text-success bg-success/10 border-success/30";
    return "text-white/40 bg-white/5 border-white/10";
  };

  return (
    <div className="w-full max-w-5xl mx-auto pb-32">
      <div className="horizon-card p-1 rounded-3xl overflow-hidden">
        <div className="bg-[#020617] rounded-[inherit]">
          
          {/* --- Header --- */}
          <div className="flex flex-col md:flex-row items-center justify-between px-10 py-10 border-b border-white/5 gap-6">
            <div className="flex flex-col gap-2">
               <h3 className="text-3xl font-heading font-bold text-white flex items-center gap-4">
                 <HistoryIcon className="w-6 h-6 text-primary" />
                 Investigation Archive
               </h3>
               <p className="text-[10px] font-mono font-bold text-white/20 uppercase tracking-[0.3em]">
                 Forensic_Registry // SECURE_STORAGE_V2
               </p>
            </div>
            
            <div className="flex items-center gap-6">
              {history.length > 0 && (
                <button
                  onClick={clearAll}
                  className="btn-horizon-outline py-2 px-4 text-[10px] text-danger border-danger/20 hover:bg-danger/5"
                >
                  Clear Archive
                </button>
              )}
              <button 
                onClick={onDismiss} 
                className="text-[10px] font-mono font-bold text-white/40 hover:text-primary tracking-widest uppercase transition-colors"
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
                  <p className="text-sm font-heading font-bold text-white/40 mb-2 uppercase tracking-widest">Archive Empty</p>
                  <p className="text-[10px] font-mono text-white/20 max-w-xs leading-relaxed">
                    System awaiting initial analysis payloads for registry sync.
                  </p>
                </div>
              </div>
            ) : (
              <div className="grid gap-6">
                {history.sort((a,b) => b.timestamp - a.timestamp).map((item, i) => (
                  <motion.div
                    key={item.sessionId}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.05 }}
                    onClick={() => onSelect(item.sessionId)}
                    className="group relative horizon-card p-6 rounded-2xl cursor-pointer hover:ring-2 hover:ring-primary/20 transition-all"
                  >
                    <div className="flex flex-col md:flex-row gap-6 items-center">
                      
                      {/* Aperture Preview */}
                      <div className="relative w-16 h-16 shrink-0 flex items-center justify-center">
                        <motion.div 
                          animate={{ rotate: 360 }}
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
                            <span className="text-[9px] font-mono font-bold text-primary/40 tracking-widest">SESSION_{item.sessionId.slice(-6)}</span>
                            <span className="text-[9px] font-mono text-white/20 uppercase tracking-tighter">[{item.type}_ANALYSIS]</span>
                         </div>
                         <h4 className="text-lg font-heading font-bold text-white/80 truncate group-hover:text-white transition-colors">
                           {item.fileName}
                         </h4>
                      </div>

                      {/* Verdict Pill */}
                      <div className={clsx(
                        "px-4 py-1.5 rounded border text-[10px] font-mono font-bold uppercase tracking-widest",
                        getVerdictStyle(item.verdict)
                      )}>
                        {item.verdict?.replace(/_/g, " ")}
                      </div>

                      {/* Actions */}
                      <div className="flex items-center gap-4">
                        <div className="text-right hidden lg:block">
                           <div className="text-[10px] font-mono text-white/20">TIMESTAMP</div>
<div className="text-[10px] font-mono text-white/60">
                              {new Date(item.timestamp).toLocaleDateString()} {new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                            </div>
                        </div>
                        <button
                          onClick={(e) => removeItem(e, item.sessionId)}
                          className="p-3 rounded-lg border border-white/5 text-white/20 hover:text-danger hover:border-danger/30 transition-all"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </div>
                    </div>

                    <div className="absolute top-0 right-0 p-1 opacity-0 group-hover:opacity-100 transition-opacity">
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
