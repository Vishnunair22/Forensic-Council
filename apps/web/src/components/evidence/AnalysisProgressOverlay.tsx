"use client";

import { ForensicProgressOverlay } from "@/components/ui/ForensicProgressOverlay";

interface AnalysisProgressOverlayProps {
  isVisible: boolean;
  title?: string;
  message?: string;
}

export function AnalysisProgressOverlay({
  isVisible,
  title = "Initializing",
  message = "Please wait...",
}: AnalysisProgressOverlayProps) {
  if (!isVisible) return null;

  return (
    <ForensicProgressOverlay
      title={title}
      liveText={message}
      telemetryLabel="Secured Transmission"
      showElapsed={true}
    />
  );
}