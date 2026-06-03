// Shared rotating status phrases for the Council Arbiter synthesis overlay.
// Single source of truth so the evidence-page and result-page arbiter overlays
// stay in lockstep (previously this array was duplicated in both components).
export const ARBITER_PHASES = [
  "Reviewing forensic agent telemetry...",
  "Evaluating confidence intervals...",
  "Cross-referencing anomaly signatures...",
  "Synthesizing executive summary...",
  "Drafting final Council verdict...",
  "Finalizing cryptographic signature...",
] as const;
