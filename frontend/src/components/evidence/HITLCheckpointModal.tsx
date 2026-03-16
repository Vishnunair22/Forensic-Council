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
              <div className="p-4 rounded-lg bg-white/5 border border-white/10">
                <h4 className="text-sm font-semibold text-slate-300 mb-2">
                  Finding Summary
                </h4>
                <p className="text-sm text-slate-300">{checkpoint.brief_text}</p>
              </div>

              {/* Decision Needed */}
              <div className="p-4 rounded-lg bg-amber-500/10 border border-amber-500/30">
                <h4 className="text-sm font-semibold text-amber-300 mb-2">
                  Action Required
                </h4>
                <p className="text-sm text-amber-200">{checkpoint.decision_needed}</p>
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
                      className={`p-3 rounded-lg border-2 transition-all text-left ${
                        selectedDecision === option.value
                          ? `border-${option.color}-500/70 bg-${option.color}-500/20`
                          : "border-white/10 bg-white/5 hover:bg-white/10"
                      }`}
                    >
                      <p className="text-sm font-semibold text-white">
                        {option.label}
                      </p>
                      <p className="text-xs text-slate-400 mt-1">
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
                  className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 resize-none"
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
            <DialogFooter>
              <button
                onClick={onDismiss}
                disabled={isSubmitting}
                className="px-4 py-2 rounded-lg border border-slate-700/30 text-slate-300 hover:bg-white/5 transition-all disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleSubmit}
                disabled={!selectedDecision || isSubmitting}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600/30 border border-emerald-500/50 text-emerald-300 hover:bg-emerald-600/50 disabled:opacity-50 transition-all font-medium"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Submitting...
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="w-4 h-4" />
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
