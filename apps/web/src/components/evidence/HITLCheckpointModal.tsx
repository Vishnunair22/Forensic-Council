"use client";

import { useState } from "react";
import {
 Dialog,
 DialogContent,
 DialogHeader,
 DialogTitle,
 DialogDescription,
 DialogFooter,
} from "@/components/ui/dialog";
import { CheckCircle2, Loader2, ShieldAlert, ArrowRight } from "lucide-react";
import { clsx } from "clsx";

interface HITLCheckpoint {
 checkpoint_id: string;
 session_id: string;
 agent_id: string;
 agent_name: string;
 brief_text: string;
 decision_needed: string;
 created_at: string;
}

type HITLDecision = "APPROVE" | "REDIRECT" | "OVERRIDE" | "TERMINATE" | "ESCALATE";

interface HITLCheckpointModalProps {
 checkpoint: HITLCheckpoint | null;
 isOpen: boolean;
 isSubmitting: boolean;
 onDecision: (decision: HITLDecision, note?: string) => Promise<void>;
 onDismiss: () => void;
}

const decisionOptions: Array<{
  value: HITLDecision;
  label: string;
  description: string;
  color: "emerald" | "cyan" | "slate" | "red";
}> = [
  { value: "APPROVE", label: "Approve", description: "Accept finding and continue", color: "emerald" },
  { value: "REDIRECT", label: "Redirect", description: "Request cross-modal review", color: "emerald" },
  { value: "OVERRIDE", label: "Override", description: "Provide alternate verdict", color: "slate" },
  { value: "TERMINATE", label: "Terminate", description: "Halt pipeline — critical risk detected", color: "red" },
  { value: "ESCALATE", label: "Escalate", description: "Flag for senior council", color: "red" },
];

export function HITLCheckpointModal({
 checkpoint,
 isOpen,
 isSubmitting,
 onDecision,
 onDismiss,
}: HITLCheckpointModalProps) {
 const [selectedDecision, setSelectedDecision] = useState<HITLDecision | null>(null);
 const [note, setNote] = useState("");
 const [decisionError, setDecisionError] = useState<string | null>(null);

 const handleSubmit = async () => {
  if (!selectedDecision) {
   setDecisionError("Please select a valid protocol decision.");
   return;
  }
  try {
   setDecisionError(null);
   await onDecision(selectedDecision, note);
   setSelectedDecision(null);
   setNote("");
  } catch (error) {
   setDecisionError(error instanceof Error ? error.message : "Protocol submission failed.");
  }
 };

 return (
  <Dialog open={isOpen} onOpenChange={onDismiss}>
   <DialogContent className="sm:max-w-xl glass-panel border-white/10 p-0 overflow-hidden rounded-3xl shadow-[0_32px_64px_rgba(0,0,0,0.8)] border-t border-t-white/10">

    {checkpoint ? (
     <div className="p-8 space-y-6">
      <DialogHeader className="text-left space-y-2">
       <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center">
         <ShieldAlert className="w-6 h-6 text-primary" />
        </div>
        <div>
         <DialogTitle className="text-2xl font-extrabold text-white px-0 tracking-tight drop-shadow-md">
          Investigator Intervention
         </DialogTitle>
         <DialogDescription className="text-sm font-mono font-medium text-white/60 tracking-wide mt-1">
          Checkpoint ID: {checkpoint.checkpoint_id.slice(0, 8)} · {checkpoint.agent_name}
         </DialogDescription>
        </div>
       </div>
      </DialogHeader>

      <div className="space-y-4">
       {/* Context Panels */}
       <div className="grid grid-cols-1 gap-4">
        <div className="p-5 rounded-2xl glass-panel bg-white/[0.02] border-white/5 space-y-2">
         <h4 className="text-[10px] font-black font-mono text-white/20 tracking-wide">Evidence Brief</h4>
         <p className="text-sm text-white/70 leading-relaxed">{checkpoint.brief_text}</p>
        </div>
        <div className="p-5 rounded-2xl bg-primary/[0.03] border border-primary/10 space-y-2">
         <h4 className="text-[10px] font-black font-mono text-primary/50 tracking-wide">Decision Required</h4>
         <p className="text-sm text-primary-200/80 leading-relaxed font-medium">{checkpoint.decision_needed}</p>
        </div>
       </div>

       {/* Decision Grid */}
       <div className="space-y-3">
        <h4 className="text-xs font-black text-white/40 tracking-wide px-1">Protocol Selection</h4>
        <div className="grid grid-cols-2 gap-3" role="radiogroup" aria-label="Protocol Selection">
          {decisionOptions.map((option) => (
           <button
            key={option.value}
            role="radio"
            aria-checked={selectedDecision === option.value}
            onClick={() => setSelectedDecision(option.value)}
            className={clsx(
              "p-5 rounded-2xl border text-left transition-all duration-300 relative overflow-hidden group",
              selectedDecision === option.value
                ? "bg-primary/10 border-primary shadow-[0_0_20px_rgba(0,255,65,0.2)]"
                : "border-white/10 bg-white/[0.02] hover:bg-primary/[0.03] hover:border-primary/40"
            )}
          >
           <div className="flex flex-col gap-1 relative z-10">
            <span className={clsx(
              "text-sm font-bold tracking-tight transition-colors",
              selectedDecision === option.value ? "text-primary" : "text-white/80 group-hover:text-white"
            )}>
             {option.label}
            </span>
            <span className="text-[10px] text-white/30 font-medium leading-tight group-hover:text-white/50 transition-colors">
             {option.description}
            </span>
           </div>
          </button>
         ))}
        </div>
       </div>

       {/* Note input */}
       <div className="space-y-3">
        <h4 className="text-xs font-black text-white/40 tracking-wide px-1">Supplemental Documentation</h4>
        <textarea
         id="hitl-notes"
         value={note}
         onChange={(e) => setNote(e.target.value)}
         placeholder="Enter forensic notes for this intervention..."
         className="w-full px-5 py-4 rounded-2xl bg-white/[0.02] border border-white/5 text-sm text-white/80 placeholder:text-white/10 focus:outline-none focus:border-primary/30 transition-all min-h-[100px] resize-none"
         disabled={isSubmitting}
        />
       </div>

       {decisionError && (
        <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-[11px] font-bold text-center tracking-wide">
         {decisionError}
        </div>
       )}
      </div>

      <DialogFooter className="sm:justify-between border-t border-white/5 p-8 pt-6 gap-4">
       <button
        onClick={onDismiss}
        disabled={isSubmitting}
        className="px-8 py-4 rounded-full border border-white/10 text-white/60 hover:text-white hover:bg-white/[0.05] transition-all text-sm font-bold tracking-wide"
       >
        Cancel
       </button>
       <button
        onClick={handleSubmit}
        disabled={!selectedDecision || isSubmitting}
        className="px-10 py-4 rounded-full bg-primary text-black font-bold text-sm tracking-wide hover:bg-primary/90 active:scale-[0.98] transition-all duration-300 shadow-[0_0_30px_rgba(0,255,65,0.25)] hover:shadow-[0_0_50px_rgba(0,255,65,0.4)] flex items-center gap-2"
       >
        {isSubmitting ? (
         <>
          <Loader2 className="w-4 h-4 animate-spin" />
          Transmitting...
         </>
        ) : (
         <>
          <CheckCircle2 className="w-4 h-4" />
          Finalize Decision
          <ArrowRight className="w-4 h-4" />
         </>
        )}
       </button>
      </DialogFooter>
     </div>
    ) : null}
   </DialogContent>
  </Dialog>
 );
}
