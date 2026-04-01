"use client";

import { ForensicProgressOverlay } from "./ForensicProgressOverlay";

export interface LoadingOverlayProps {
  /** Single live line from the pipeline (HTTP phase text, WS message, etc.). */
  liveText?: string;
}

/**
 * Landing → evidence transition overlay. Prefer passing `liveText` from the
 * parent so users see real backend / upload progress instead of canned copy.
 */
export function LoadingOverlay({ liveText }: LoadingOverlayProps) {
  return (
    <ForensicProgressOverlay
      variant="stream"
      title="Forensic stream"
      liveText={
        liveText?.trim() ||
        "Secure session hand-off in progress — connecting telemetry…"
      }
      telemetryLabel="Evidence analysis"
      showElapsed
    />
  );
}
