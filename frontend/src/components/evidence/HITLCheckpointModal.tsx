/**
 * HITLCheckpointModal Component
 * =============================
 * 
 * Displays a modal for human-in-the-loop checkpoints during analysis.
 * Allows investigators to make decisions on agent findings.
 */

import { useState } from "react";
import { motion } from "framer-motion";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";

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

export function HITLCheckpointModal({
  checkpoint,
  isOpen,
  isSubmitting,
  onDecision,
  onDismiss,
}: HITLCheckpointModalProps) {
  const [selectedDecision, setSelectedDecision] = useState<HITLDecision | null>(
    null
  );
  const [note, setNote] = useState("");
  const [decisionError, setDecisionError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!selectedDecision) {
      setDecisionError("Please select a decision");
      return;
    }

    try {
      setDecisionError(null);
      await onDecision(selectedDecision, note);
      // Reset on success
      setSelectedDecision(null);
      setNote("");
    } catch (error) {
      setDecisionError(
        error instanceof Error ? error.message : "Failed to submit decision"
      );
    }
  };

  const decisionOptions: Array<{
    value: HITLDecision;
    label: string;
    description: string;
    color: string;
  }> = [
    {
      value: "APPROVE",
      label: "Approve",
      description: "Accept this finding and continue",
      color: "emerald",
    },
    {
      value: "REDIRECT",
      label: "Redirect",
      description: "Send to different agent for review",
      color: "blue",
    },
    {
      value: "OVERRIDE",
      label: "Override",
      description: "Reject and provide alternate conclusion",
      color: "amber",
    },
    {
      value: "ESCALATE",
      label: "Escalate",
      description: "Flag for senior investigator review",
      color: "red",
    },
  ];

  return (
    <Dialog open={isOpen} onOpenChange={onDismiss}>
      <DialogContent className="sm:max-w-lg">
        {checkpoint ? (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-amber-400" />
                Investigator Decision Required
              </DialogTitle>
              <DialogDescription className="text-sm text-slate-400 mt-2">
                Agent {checkpoint.agent_name} has flagged a finding that requires
                your assessment.
              </DialogDescription>
            </DialogHeader>

            {/* Checkpoint Details */}
            <div className="space-y-4 my-6">
              {/* Brief */}
              <div className="p-4 rounded-xl glass-panel border border-white/[0.08]">
                <h4 className="text-xs font-mono text-slate-500 uppercase tracking-widest mb-2">
                  Finding Summary
                </h4>
                <p className="text-sm text-slate-300 leading-relaxed">{checkpoint.brief_text}</p>
              </div>

              {/* Decision Needed */}
              <div className="p-4 rounded-xl bg-amber-500/[0.06] border border-amber-500/[0.25] backdrop-blur-sm">
                <h4 className="text-xs font-mono text-amber-400 uppercase tracking-widest mb-2">
                  Action Required
                </h4>
                <p className="text-sm text-amber-200 leading-relaxed">{checkpoint.decision_needed}</p>
              </div>

              {/* Decision Options */}
              <div className="space-y-3">
                <h4 className="text-sm font-semibold text-slate-300">
                  Your Decision
                </h4>
                <div className="grid grid-cols-2 gap-3">
                  {decisionOptions.map((option) => (
                    <motion.button
                      key={option.value}
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                      onClick={() => setSelectedDecision(option.value)}
                      className={`p-3 rounded-xl border transition-all text-left backdrop-blur-sm ${
                        selectedDecision === option.value
                          ? option.color === "emerald"
                            ? "border-emerald-500/60 bg-emerald-500/15 shadow-[0_0_16px_rgba(16,185,129,0.15)]"
                            : option.color === "blue"
                              ? "border-blue-500/60 bg-blue-500/15 shadow-[0_0_16px_rgba(59,130,246,0.15)]"
                              : option.color === "amber"
                                ? "border-amber-500/60 bg-amber-500/15 shadow-[0_0_16px_rgba(245,158,11,0.15)]"
                                : "border-red-500/60 bg-red-500/15 shadow-[0_0_16px_rgba(239,68,68,0.15)]"
                          : "border-white/[0.08] bg-white/[0.03] hover:bg-white/[0.06] hover:border-white/[0.14]"
                      }`}
                    >
                      <p className="text-sm font-semibold text-white">
                        {option.label}
                      </p>
                      <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">
                        {option.description}
                      </p>
                    </motion.button>
                  ))}
                </div>
              </div>

              {/* Notes */}
              <div>
                <label htmlFor="hitl-notes" className="text-sm font-semibold text-slate-300 mb-2 block">
                  Additional Notes (Optional)
                </label>
                <textarea
                  id="hitl-notes"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Explain your decision or provide additional context..."
                  className="w-full px-3 py-2.5 rounded-xl bg-white/[0.04] border border-white/[0.10] text-sm text-white placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:border-emerald-500/40 resize-none backdrop-blur-sm transition-colors"
                  rows={3}
                  disabled={isSubmitting}
                />
              </div>

              {/* Error Message */}
              {decisionError && (
                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 text-sm"
                >
                  {decisionError}
                </motion.div>
              )}
            </div>

            {/* Footer with Actions */}
            <DialogFooter className="gap-2 mt-2">
              <button
                onClick={onDismiss}
                disabled={isSubmitting}
                className="btn btn-ghost px-4 py-2.5 rounded-xl disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleSubmit}
                disabled={!selectedDecision || isSubmitting}
                className="btn btn-primary px-4 py-2.5 rounded-xl font-semibold disabled:opacity-50"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                    Submitting…
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="w-4 h-4" aria-hidden="true" />
                    Submit Decision
                  </>
                )}
              </button>
            </DialogFooter>
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
