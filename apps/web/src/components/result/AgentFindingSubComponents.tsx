"use client";

import React, { useState } from "react";
import { 
 ChevronDown, 
 Clock, 
 AlertTriangle, 
 CheckCircle2, 
 XCircle 
} from "lucide-react";
import { clsx } from "clsx";
import { fmtTool } from "@/lib/fmtTool";
import { getToolIcon } from "@/lib/tool-icons";
import type { AgentFindingDTO } from "@/lib/api";

// ─── Confidence Bar Component ───
export function ConfidenceBar({ value }: { value: number }) {
 const filled = Math.round(value * 5);
 const color = value >= 0.75 ? "bg-primary" : value >= 0.5 ? "bg-warning" : "bg-danger";
 const textColor = value >= 0.75 ? "text-primary" : value >= 0.5 ? "text-warning" : "text-danger";

 return (
  <div className="flex items-center gap-3">
   <div className="flex gap-1.5">
    {Array.from({ length: 5 }).map((_, i) => (
     <div
      key={i}
      className={clsx(
       "h-1 rounded-full transition-all duration-700",
       i < filled ? color : "bg-white/5",
       i < filled ? "w-6 shadow-[0_0_10px_rgba(34,211,238,0.5)]" : "w-1.5"
      )}
     />
    ))}
   </div>
   <span className={clsx("text-[10px] font-black font-mono tabular-nums", textColor)}>
    {Math.round(value * 100)}%
   </span>
  </div>
 );
}

// ─── Tool Row Component ───
export function ToolRow({ 
 finding, 
 isLast 
}: { 
 finding: AgentFindingDTO; 
 isLast: boolean; 
}) {
 const [expanded, setExpanded] = useState(false);
 const toolName = (finding.metadata?.tool_name as string) || finding.finding_type;
 
 const na = finding.metadata?.ela_not_applicable || finding.metadata?.ghost_not_applicable;
 const status = na ? "na" : (finding.status === "CONFIRMED" ? "success" : (finding.status === "ERROR" ? "error" : "warning"));
 
 const Icon = getToolIcon(toolName);
 const timingMs = (finding.metadata?.execution_time_ms as number) || null;
 const confidence = finding.raw_confidence_score || 0;

 return (
  <div className={clsx("group", !isLast && "border-b border-white/[0.03]")}>
   <button
    onClick={() => setExpanded(!expanded)}
    className={clsx(
     "w-full flex items-center gap-4 px-6 py-4 text-left transition-all",
     expanded ? "bg-white/[0.03]" : "hover:bg-white/[0.01]"
    )}
    aria-expanded={expanded}
    aria-controls={`tool-content-${toolName}`}
   >
    <div className={clsx(
     "w-9 h-9 rounded-xl flex items-center justify-center shrink-0 border shadow-md",
     status === "success" ? "bg-primary/10 border-primary/20 text-primary" :
     status === "warning" ? "bg-warning/10 border-warning/20 text-warning" :
     status === "error" ? "bg-danger/10 border-danger/20 text-danger" :
     "bg-surface-1 border-border-subtle text-white/20"
    )}>
     <Icon className="w-4 h-4" />
    </div>

    <span className="flex-1 text-[10px] font-black tracking-[0.2em] text-white/60 group-hover:text-white transition-colors uppercase">
     {fmtTool(toolName)}
    </span>

    <div className="flex items-center gap-4 shrink-0">
     {timingMs && (
      <span className="text-[10px] font-mono text-white/20 flex items-center gap-1.5">
       <Clock className="w-3 h-3" /> {timingMs >= 1000 ? `${(timingMs/1000).toFixed(1)}s` : `${timingMs}ms`}
      </span>
     )}
     
     <div className={clsx(
      "px-3 py-1 rounded-full border text-[9px] font-black tracking-[0.2em] uppercase",
      status === "success" ? "bg-primary/10 border-primary/20 text-primary" : 
      status === "error" ? "bg-danger/10 border-danger/20 text-danger" : 
      status === "na" ? "bg-surface-1 border-border-subtle text-white/20" : 
      "bg-warning/10 border-warning/20 text-warning"
     )}>
      {status === "success" ? "Valid" : status === "warning" ? "Flagged" : status.toUpperCase()}
     </div>

     {!na && (
      <span className={clsx(
       "text-[10px] font-black font-mono w-10 text-right tabular-nums",
       confidence >= 0.75 ? "text-primary" : confidence >= 0.5 ? "text-warning" : "text-danger"
      )}>
       {Math.round(confidence * 100)}%
      </span>
     )}

     <ChevronDown className={clsx("w-3.5 h-3.5 text-white/20 transition-transform duration-300", expanded && "rotate-180 text-white/50")} />
    </div>
   </button>

   {expanded && (
    <div id={`tool-content-${toolName}`} className="px-6 pb-6 pt-2">
     <div className="p-6 rounded-[1.5rem] premium-card space-y-5 shadow-inner">
      {/* Per-tool specific signal — raw output from the tool */}
      <div className="space-y-2">
       <h5 className="text-[9px] font-black text-white/20 tracking-[0.3em] uppercase">Diagnostic Intelligence</h5>
       <p className="text-[13px] text-white/70 leading-relaxed font-medium font-mono uppercase tracking-tight">
        {(finding.metadata?.raw_tool_summary as string) || finding.reasoning_summary || "No diagnostic output."}
       </p>
      </div>

      {/* Section key signal (quick one-liner verdict) */}
      {(finding.metadata?.section_key_signal as string) && (
       <div className="flex items-start gap-2 p-3 rounded-xl bg-white/[0.03] border border-white/5">
        <CheckCircle2 className="w-3.5 h-3.5 text-white/50 mt-0.5 shrink-0" />
        <p className="text-[11px] text-white/40 leading-relaxed italic">
         {finding.metadata?.section_key_signal as string}
        </p>
       </div>
      )}

      {finding.status === "ERROR" && (
       <div className="flex items-center gap-2 p-3 rounded-xl bg-rose-500/5 border border-rose-500/10 text-rose-400 text-[10px] font-bold tracking-widest">
        <XCircle className="w-3.5 h-3.5" /> Analysis Protocol Error
       </div>
      )}

      {finding.status === "INCOMPLETE" && (
       <div className="flex items-center gap-2 p-3 rounded-xl bg-amber-500/5 border border-amber-500/10 text-amber-400 text-[10px] font-bold tracking-widest">
        <AlertTriangle className="w-3.5 h-3.5" /> No Matching Tool — Task Not Executed
       </div>
      )}
     </div>
    </div>
   )}
  </div>
 );
}

// ─── More Findings Component ───
export function MoreFindingsToggle({ findings, count }: { findings: AgentFindingDTO[]; count: number }) {
 const [open, setOpen] = useState(false);
 const issues = findings.filter(f => f.status === "FLAGGED" || f.status === "ERROR").length;

 return (
  <div className="border-t border-white/[0.03]">
   <button
    onClick={() => setOpen(!open)}
    className="w-full flex items-center justify-between px-6 py-4 hover:bg-white/[0.02] transition-all group"
   >
    <div className="flex items-center gap-3">
     <span className="text-[10px] font-black tracking-[0.2em] text-white/50 group-hover:text-white/50 transition-colors">
      {open ? "Condense Analysis" : `+${count} Additional Signal${count > 1 ? "s" : ""}`}
     </span>
     {!open && issues > 0 && (
      <span className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-rose-500/10 border border-rose-500/20 text-rose-400 text-[10px] font-bold">
       <AlertTriangle className="w-2.5 h-2.5" /> {issues} ISSUE{issues > 1 ? "S" : ""}
      </span>
     )}
    </div>
    <ChevronDown className={clsx("w-4 h-4 text-white/20 transition-transform duration-300", open && "rotate-180")} />
   </button>

   {open && (
    <div className="animate-in fade-in slide-in-from-top-2 duration-300">
     {findings.map((f, i) => (
      <ToolRow key={f.finding_id ?? `${f.finding_type}-${i}`} finding={f} isLast={i === findings.length - 1} />
     ))}
    </div>
   )}
  </div>
 );
}
