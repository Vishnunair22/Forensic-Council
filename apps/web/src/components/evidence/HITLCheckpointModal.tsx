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
import { ShieldAlert, ArrowRight } from "lucide-react";
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

// Visual language for the option grid: green = constructive (approve/redirect),
// blue = neutral (override), red = destructive (terminate/escalate). Previously
// the `color` field was unused, so every option looked identical regardless of
// how consequential it was.
const OPTION_STYLES: Record<string, { selected: string; idle: string; ring: string }> = {
  emerald: {
    selected: "bg-success/10 border-success fc-text-primary",
    idle: "border-white/10 bg-white/5 hover:bg-white/10 fc-text-secondary hover:fc-text-primary",
    ring: "focus-visible:ring-success/50",
  },
  red: {
    selected: "bg-danger/10 border-danger fc-text-danger",
    idle: "border-danger/25 bg-danger/[0.04] fc-text-secondary hover:bg-danger/10 hover:fc-text-danger",
    ring: "focus-visible:ring-danger/50",
  },
  slate: {
    selected: "bg-primary/10 border-primary fc-text-primary",
    idle: "border-white/10 bg-white/5 hover:bg-white/10 fc-text-secondary hover:fc-text-primary",
    ring: "focus-visible:ring-primary/50",
  },
  default: {
    selected: "bg-primary/10 border-primary fc-text-primary",
    idle: "border-white/10 bg-white/5 hover:bg-white/10 fc-text-secondary hover:fc-text-primary",
    ring: "focus-visible:ring-primary/50",
  },
};

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
  setDecisionError(null);
  await onDecision(selectedDecision, note);
  setSelectedDecision(null);
  setNote("");
 };

 return (
   <Dialog open={isOpen && !!checkpoint} onOpenChange={handleDismiss}>
    <DialogContent className="sm:max-w-xl p-0">

     {checkpoint ? (
     <div className="p-8 space-y-6 flex flex-col text-left">
      <DialogHeader className="text-left space-y-2">
       <div className="flex items-center gap-3">
        <div className="w-10 h-10 border border-white/20 bg-white/5 flex items-center justify-center rounded-2xl">
         <ShieldAlert className="w-5 h-5 text-white/70" />
        </div>
        <div>
         <DialogTitle className="text-2xl font-heading font-bold fc-text-primary tracking-tight">
          Investigator Intervention
         </DialogTitle>
         <DialogDescription className="fc-eyebrow fc-text-muted mt-1">
          Checkpoint ID: {checkpoint.checkpoint_id.slice(0, 8)} · {checkpoint.agent_name}
         </DialogDescription>
        </div>
       </div>
      </DialogHeader>

      <div className="space-y-4">
       {/* Context Panels */}
       <div className="grid grid-cols-1 gap-4">
        <div className="border-l-2 border-white/20 pl-4 py-1 space-y-2">
         <h4 className="fc-eyebrow fc-text-muted">Evidence Brief</h4>
         <p className="text-sm fc-text-secondary leading-relaxed">{checkpoint.brief_text}</p>
        </div>
        <div className="border-l-2 border-primary pl-4 py-1 space-y-2 bg-primary/5">
         <h4 className="fc-eyebrow text-primary">Decision Required</h4>
         <p className="text-sm fc-text-primary leading-relaxed font-bold">{checkpoint.decision_needed}</p>
        </div>
       </div>

       {/* Decision Grid */}
       <div className="space-y-3 pt-4 border-t border-white/5">
        <h4 className="fc-eyebrow fc-text-muted mb-2" id="protocol-selection-label">Protocol Selection</h4>
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
          {decisionOptions.map((option) => {
           const s = OPTION_STYLES[option.color] ?? OPTION_STYLES.default;
           return (
           <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={selectedDecision === option.value}
            tabIndex={selectedDecision === option.value || (!selectedDecision && option.value === "APPROVE") ? 0 : -1}
            onClick={() => setSelectedDecision(option.value)}
            className={clsx(
              "p-4 border text-left transition-colors duration-[160ms] rounded-2xl text-sm relative outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-offset-background",
              s.ring,
              selectedDecision === option.value ? s.selected : s.idle
            )}
          >
           <div className="flex flex-col gap-1 relative z-10">
            <span className={clsx(
              "font-bold tracking-tight transition-colors",
              selectedDecision === option.value ? "fc-text-primary" : ""
            )}>
             {option.label}
            </span>
            <span className={clsx(
              "text-xs font-mono leading-tight transition-colors",
              selectedDecision === option.value ? "fc-text-secondary" : "fc-text-muted"
            )}>
             {option.description}
            </span>
           </div>
          </button>
           );
          })}
        </div>
       </div>

        {/* Note input */}
        <div className="space-y-3">
         <h4 className="fc-eyebrow fc-text-muted" id="hitl-notes-label">Supplemental Documentation</h4>
         <textarea
          id="hitl-notes"
          aria-labelledby="hitl-notes-label"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Enter forensic notes for this intervention..."
          className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-2xl text-sm fc-text-primary placeholder:fc-text-faint outline-none focus-visible:ring-2 focus-visible:ring-primary/50 focus-visible:ring-offset-1 focus-visible:ring-offset-background focus-visible:border-white/30 transition-colors min-h-[100px] resize-none"
          disabled={isSubmitting}
        />
        </div>

        {decisionError && (
         <div role="alert" className="p-3 rounded-xl bg-danger/10 border border-danger/20 fc-text-danger text-xs font-bold text-center tracking-wide">
          {decisionError}
         </div>
        )}
      </div>

      <DialogFooter className="sm:justify-between border-t border-white/5 p-8 pt-6 gap-4">
        <button
         type="button"
         onClick={handleDismiss}
         disabled={isSubmitting}
         className="fc-btn-secondary"
        >
         Cancel
        </button>
        <button
         type="button"
         onClick={handleSubmit}
         disabled={!selectedDecision || isSubmitting}
         className={clsx(
          "flex items-center gap-2 disabled:opacity-[0.48]",
          selectedDecision === "TERMINATE" || selectedDecision === "ESCALATE" ? "fc-btn-danger" : "fc-btn-primary"
         )}
        >
        {isSubmitting ? (
         <>
          <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          Submitting…
         </>
        ) : (
         <>
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
