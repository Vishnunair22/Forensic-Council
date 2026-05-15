"use client";

import { useState, useCallback, useEffect } from "react";
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

  // F-H-7 (forensic-critical): reset local state when a NEW checkpoint arrives
  // in the same mounted instance. Without this, the previously-selected
  // decision/note from the prior checkpoint persist and the investigator could
  // inadvertently submit them against a different checkpoint.
  useEffect(() => {
    setSelectedDecision(null);
    setNote("");
    setDecisionError(null);
  }, [checkpoint?.checkpoint_id]);

  const handleDismiss = useCallback(() => {
    setSelectedDecision(null);
    setNote("");
    setDecisionError(null);
    onDismiss();
  }, [onDismiss]);

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
   <Dialog open={isOpen} onOpenChange={handleDismiss}>
    <DialogContent className="sm:max-w-xl bg-[#06090E] border border-[#333333] p-0 overflow-hidden shadow-2xl rounded-none">

     {checkpoint ? (
     <div className="p-8 space-y-6">
      <DialogHeader className="text-left space-y-2">
       <div className="flex items-center gap-3">
        <div className="w-12 h-12 bg-white flex items-center justify-center">
         <ShieldAlert className="w-7 h-7 text-black" />
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
        <div className="p-5 bg-[#111111] border border-[#333333] space-y-2">
         <h4 className="text-[10px] font-black font-mono text-white/50 tracking-wide uppercase">Evidence Brief</h4>
         <p className="text-sm text-white/80 leading-relaxed">{checkpoint.brief_text}</p>
        </div>
        <div className="p-5 bg-white border border-white space-y-2">
         <h4 className="text-[10px] font-black font-mono text-black/60 tracking-wide uppercase">Decision Required</h4>
         <p className="text-sm text-black leading-relaxed font-bold">{checkpoint.decision_needed}</p>
        </div>
       </div>

       {/* Decision Grid */}
       <div className="space-y-3">
        <h4 className="text-xs font-black text-white/40 tracking-wide px-1" id="protocol-selection-label">Protocol Selection</h4>
        <div
          className="grid grid-cols-2 gap-3"
          role="radiogroup"
          tabIndex={-1}
          aria-labelledby="protocol-selection-label"
          onKeyDown={(e) => {
            const options = decisionOptions.map((o) => o.value);
            const currentIndex = selectedDecision ? options.indexOf(selectedDecision) : -1;
            if (e.key === "ArrowRight" || e.key === "ArrowDown") {
              e.preventDefault();
              const next = options[(currentIndex + 1) % options.length];
              setSelectedDecision(next);
              (e.currentTarget.querySelectorAll('[role="radio"]')[options.indexOf(next)] as HTMLElement)?.focus();
            } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
              e.preventDefault();
              const prev = options[(currentIndex - 1 + options.length) % options.length];
              setSelectedDecision(prev);
              (e.currentTarget.querySelectorAll('[role="radio"]')[options.indexOf(prev)] as HTMLElement)?.focus();
            }
          }}
        >
          {decisionOptions.map((option) => (
           <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={selectedDecision === option.value}
            tabIndex={selectedDecision === option.value || (!selectedDecision && option.value === "APPROVE") ? 0 : -1}
            onClick={() => setSelectedDecision(option.value)}
            className={clsx(
              "p-5 border text-left transition-colors duration-200 relative",
              selectedDecision === option.value
                ? "bg-white border-white text-black"
                : "border-[#333333] bg-[#111111] hover:bg-[#1A1A1A]"
            )}
          >
           <div className="flex flex-col gap-1 relative z-10">
            <span className={clsx(
              "text-sm font-bold tracking-tight transition-colors",
              selectedDecision === option.value ? "text-black" : "text-white"
            )}>
             {option.label}
            </span>
            <span className={clsx(
              "text-[10px] font-medium leading-tight transition-colors",
              selectedDecision === option.value ? "text-black/70" : "text-white/50"
            )}>
             {option.description}
            </span>
           </div>
          </button>
         ))}
        </div>
       </div>

{/* Note input */}
        <div className="space-y-3">
         <h4 className="text-xs font-black text-white/40 tracking-wide px-1" id="hitl-notes-label">Supplemental Documentation</h4>
         <textarea
          id="hitl-notes"
          aria-labelledby="hitl-notes-label"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Enter forensic notes for this intervention..."
          className="w-full px-5 py-4 bg-[#111111] border border-[#333333] text-sm text-white placeholder:text-white/20 focus:outline-none focus:border-white transition-colors min-h-[100px] resize-none"
          disabled={isSubmitting}
        />
        </div>

        {decisionError && (
         <div role="alert" className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-[11px] font-bold text-center tracking-wide">
          {decisionError}
         </div>
        )}
      </div>

<DialogFooter className="sm:justify-between border-t border-[#333333] p-8 pt-6 gap-4 bg-[#06090E]">
        <button
         type="button"
         onClick={onDismiss}
         disabled={isSubmitting}
         className="px-8 py-4 border border-[#333333] text-white/60 hover:text-white hover:bg-[#111111] transition-colors text-sm font-bold tracking-wide uppercase"
        >
         Cancel
        </button>
        <button
         type="button"
         onClick={handleSubmit}
         disabled={!selectedDecision || isSubmitting}
         className="px-10 py-4 bg-white text-black font-bold text-sm tracking-widest uppercase hover:bg-gray-200 active:bg-gray-300 transition-colors flex items-center gap-2 disabled:opacity-50"
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
