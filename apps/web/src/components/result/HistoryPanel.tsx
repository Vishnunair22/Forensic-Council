"use client";

import React, { useCallback, useState } from "react";
import {
  ArrowRight,
  CheckSquare,
  History as HistoryIcon,
  Image as ImageIcon,
  Film,
  FileText,
  Mic,
  Square,
  Trash2,
} from "lucide-react";
import { clsx } from "clsx";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { type HistoryItem } from "@/lib/types";
import { getVerdictConfig } from "@/lib/verdict";
import { useSessionStorage } from "@/hooks/useSessionStorage";
import { STORAGE_KEYS } from "@/lib/storageKeys";

interface HistoryPanelProps {
  onSelect: (sessionId: string) => void;
  currentSessionId?: string | null;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatHistoryDate(timestamp: number): string {
  try {
    const d = new Date(timestamp);
    const day = d.getDate();
    const mod = day % 100;
    const ordinals = ["th", "st", "nd", "rd"];
    const suffix = ordinals[(mod - 20) % 10] ?? ordinals[mod] ?? "th";
    const month = d.toLocaleDateString("en-US", { month: "short" });
    const year = d.getFullYear();
    const time = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
    return `${month} ${day}${suffix} ${year} · ${time}`;
  } catch {
    return new Date(timestamp).toLocaleString();
  }
}

function mimeCategory(mime?: string | null): "image" | "video" | "audio" | "doc" {
  if (!mime) return "doc";
  if (mime.startsWith("image/")) return "image";
  if (mime.startsWith("video/")) return "video";
  if (mime.startsWith("audio/")) return "audio";
  return "doc";
}

const CAT_ICON = { image: ImageIcon, video: Film, audio: Mic, doc: FileText } as const;
const CAT_COLOR = { image: "#22d3ee", video: "#38bdf8", audio: "#818cf8", doc: "#60a5fa" } as const;

function HistoryThumbnail({ thumbnail, mime, fileName }: { thumbnail?: string; mime?: string; fileName: string }) {
  const cat = mimeCategory(mime);
  const Icon = CAT_ICON[cat];
  const color = CAT_COLOR[cat];

  if ((cat === "image" || cat === "video") && thumbnail) {
    return (
      /* eslint-disable-next-line @next/next/no-img-element */
      <img src={thumbnail} alt={fileName} className="w-full h-full object-cover" loading="lazy" decoding="async" />
    );
  }
  return (
    /* F-8 fix: icon fallback must have a text alternative when there is no img element.
       Use role="img" + aria-label on the wrapper so AT announces the media type. */
    <div
      className="w-full h-full flex items-center justify-center"
      style={{ background: `${color}12` }}
      role="img"
      aria-label={`${cat} file`}
    >
      <Icon className="w-4 h-4" style={{ color }} aria-hidden="true" />
    </div>
  );
}

function ConfidencePill({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 75 ? "text-success" : pct >= 50 ? "text-warning" : "text-danger";
  return <span className={clsx("text-xs font-mono font-bold tabular-nums", color)}>{pct}%</span>;
}

// ── Main Component ────────────────────────────────────────────────────────────

export function HistoryPanel({ onSelect, currentSessionId }: HistoryPanelProps) {
  const [history, setHistory] = useSessionStorage<HistoryItem[]>(STORAGE_KEYS.HISTORY, [], true);
  const shouldReduceMotion = useReducedMotion();

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [showClearConfirm, setShowClearConfirm] = useState(false);

  const sorted = [...history].sort((a, b) => b.timestamp - a.timestamp);
  const isSelectMode = selectedIds.size > 0;
  const allSelected = sorted.length > 0 && selectedIds.size === sorted.length;

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    if (allSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(sorted.map((h) => h.sessionId)));
    }
  }, [allSelected, sorted]);

  const deleteSelected = useCallback(() => {
    setHistory((prev) => prev.filter((h) => !selectedIds.has(h.sessionId)));
    setSelectedIds(new Set());
  }, [selectedIds, setHistory]);

  const clearAll = useCallback(() => {
    setHistory([]);
    setSelectedIds(new Set());
    setShowClearConfirm(false);
  }, [setHistory]);

  const handleRowClick = useCallback((sessionId: string) => {
    if (isSelectMode) {
      toggleSelect(sessionId);
    } else {
      onSelect(sessionId);
    }
  }, [isSelectMode, toggleSelect, onSelect]);

  return (
    <div className="w-full max-w-4xl mx-auto pb-32 relative">
      <div className="rounded-2xl overflow-hidden fc-surface">

        {/* ── Header ── */}
        <div className="px-6 py-5 border-b border-white/[0.06] flex items-center gap-3">
          <HistoryIcon className="w-4 h-4 text-primary/60 shrink-0" />
          <h2 className="text-sm font-bold fc-text-secondary flex-1">Investigation Archive</h2>
          <span className="fc-eyebrow fc-text-muted">{sorted.length} record{sorted.length === 1 ? "" : "s"}</span>

          {/* Select all */}
          {sorted.length > 0 && (
            <button
              type="button"
              onClick={toggleSelectAll}
              aria-label={allSelected ? "Deselect all" : "Select all"}
              className="flex items-center gap-1.5 fc-eyebrow fc-text-muted hover:text-white/70 transition-colors px-2 py-1 rounded hover:bg-white/[0.04]"
            >
              {allSelected
                ? <CheckSquare className="w-3.5 h-3.5 text-primary" />
                : <Square className="w-3.5 h-3.5" />
              }
              {allSelected ? "Deselect all" : "Select all"}
            </button>
          )}

          {/* Clear All */}
          {sorted.length > 0 && !showClearConfirm && (
            <button
              type="button"
              onClick={() => setShowClearConfirm(true)}
              className="fc-eyebrow fc-text-muted hover:text-danger transition-colors px-2 py-1 rounded hover:bg-danger/5"
            >
              Clear all
            </button>
          )}
          {showClearConfirm && (
            <div className="flex items-center gap-2 bg-danger/10 border border-danger/20 rounded-lg px-2 py-1">
              <span className="fc-eyebrow text-danger">Confirm?</span>
              <button type="button" onClick={clearAll} className="fc-eyebrow text-danger font-bold hover:text-white transition-colors">Yes</button>
              <button type="button" onClick={() => setShowClearConfirm(false)} className="fc-eyebrow fc-text-muted hover:text-white/70 transition-colors">No</button>
            </div>
          )}
        </div>

        {/* ── List ── */}
        {sorted.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 gap-4">
            <div className="w-12 h-12 rounded-full border border-white/[0.06] border-dashed flex items-center justify-center">
              <HistoryIcon className="w-5 h-5 text-white/10" />
            </div>
            <p className="text-sm fc-text-muted">No investigations archived yet.</p>
          </div>
        ) : (
          <div role="list" aria-label="Investigation archive">
            {sorted.map((item, i) => {
              const vc = getVerdictConfig(item.verdict);
              const isCurrent = item.sessionId === currentSessionId;
              const isSelected = selectedIds.has(item.sessionId);

              return (
                <motion.div
                  key={item.sessionId}
                  role="listitem"
                  initial={shouldReduceMotion ? {} : { opacity: 0, y: 4 }}
                  animate={shouldReduceMotion ? {} : { opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.03, duration: 0.16, ease: "easeOut" }}
                  className={clsx(
                    "group relative flex items-center gap-3 px-5 py-4 border-b border-white/[0.04] last:border-0 transition-colors duration-[160ms]",
                    isSelected ? "bg-primary/[0.04]" : "hover:bg-white/[0.02]"
                  )}
                >
                  {/* Checkbox */}
                  <button
                    type="button"
                    onClick={() => toggleSelect(item.sessionId)}
                    aria-label={isSelected ? `Deselect ${item.fileName}` : `Select ${item.fileName}`}
                    aria-pressed={isSelected}
                    className={clsx(
                      "shrink-0 w-4 h-4 flex items-center justify-center transition-opacity duration-[160ms]",
                      isSelectMode ? "opacity-100" : "opacity-0 group-hover:opacity-100"
                    )}
                  >
                    {isSelected
                      ? <CheckSquare className="w-4 h-4 text-primary" />
                      : <Square className="w-4 h-4 fc-text-muted" />
                    }
                  </button>

                  {/* Thumbnail */}
                  <div className="shrink-0 w-10 h-10 rounded-lg border border-white/[0.08] overflow-hidden bg-white/[0.03]">
                    <HistoryThumbnail thumbnail={item.thumbnail} mime={item.mime} fileName={item.fileName} />
                  </div>

                  {/* Main content — clickable area for row navigation / select */}
                  <button
                    type="button"
                    onClick={() => handleRowClick(item.sessionId)}
                    className="flex-1 min-w-0 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 rounded"
                    aria-label={`${isSelectMode ? "Toggle selection for" : "View analysis for"} ${item.fileName}`}
                  >
                    {/* Row 1: filename + current badge + verdict */}
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-sm font-medium fc-text-secondary truncate flex-1 min-w-0">
                        {item.fileName}
                      </span>
                      {isCurrent && (
                        <span className="shrink-0 fc-eyebrow text-primary border border-primary/30 bg-primary/5 px-1.5 py-0.5 rounded">
                          Current
                        </span>
                      )}
                      <span className={clsx(
                        "shrink-0 fc-eyebrow px-2 py-0.5 rounded border",
                        vc.color === "emerald" && "text-success border-success/25 bg-success/5",
                        vc.color === "red"     && "text-danger  border-danger/25  bg-danger/5",
                        vc.color === "amber"   && "text-warning border-warning/25 bg-warning/5",
                      )}>
                        {vc.label}
                      </span>
                    </div>

                    {/* Row 2: date · confidence */}
                    <div className="flex items-center gap-2 mt-1.5">
                      <span className="text-xs font-mono fc-text-muted">{formatHistoryDate(item.timestamp)}</span>
                      {item.confidence != null && (
                        <>
                          <span className="fc-text-muted text-xs">·</span>
                          <ConfidencePill value={item.confidence} />
                        </>
                      )}
                      <span className="fc-eyebrow fc-text-muted ml-0.5">{item.type}</span>
                    </div>
                  </button>

                  {/* Arrow — always navigates, even in select mode */}
                  <button
                    type="button"
                    onClick={() => onSelect(item.sessionId)}
                    aria-label={`Open analysis for ${item.fileName}`}
                    className="shrink-0 w-7 h-7 flex items-center justify-center rounded-lg border border-white/[0.08] fc-text-muted hover:text-white hover:border-white/[0.18] hover:bg-white/[0.05] transition-all duration-[160ms] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
                  >
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </motion.div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Floating Delete Bar ── */}
      <AnimatePresence>
        {selectedIds.size > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 12 }}
            transition={{ duration: 0.16, ease: "easeOut" }}
            className="fixed bottom-8 left-1/2 -translate-x-1/2 z-50 flex items-center gap-4 px-5 py-3 rounded-2xl shadow-2xl fc-surface-overlay"
          >
            <span className="fc-eyebrow fc-text-secondary">
              {selectedIds.size} selected
            </span>
            <div className="h-4 w-px bg-white/[0.10]" />
            <button
              type="button"
              onClick={deleteSelected}
              className="flex items-center gap-2 fc-eyebrow text-danger hover:text-white hover:bg-danger px-3 py-1.5 rounded-lg border border-danger/30 hover:border-danger transition-all duration-[160ms] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger/50"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Delete selected
            </button>
            <button
              type="button"
              onClick={() => setSelectedIds(new Set())}
              className="fc-eyebrow fc-text-muted hover:text-white/70 transition-colors px-2 py-1 rounded"
            >
              Cancel
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
