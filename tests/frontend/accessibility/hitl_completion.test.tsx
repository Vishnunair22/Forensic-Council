import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { HITLCheckpointModal } from "@/components/evidence/HITLCheckpointModal";
import { ForensicProgressOverlay } from "@/components/ui/ForensicProgressOverlay";

const mockCheckpoint = {
  checkpoint_id: "cp-1",
  session_id: "sess-1",
  agent_id: "Agent1",
  agent_name: "Image Analyst",
  brief_text: "Inconsistent metadata found.",
  decision_needed: "Review and confirm the finding.",
  created_at: "2025-01-01T12:00:00Z",
};

describe("HITLCheckpointModal accessibility", () => {
  const onDecision = jest.fn();
  const onDismiss = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders an accessible review heading", () => {
    render(
      <HITLCheckpointModal
        checkpoint={mockCheckpoint}
        isOpen={true}
        isSubmitting={false}
        onDecision={onDecision}
        onDismiss={onDismiss}
      />,
    );

    expect(
      screen.getByRole("heading", { name: /human review required/i }),
    ).toBeInTheDocument();
  });

  it("shows the decision context text", () => {
    render(
      <HITLCheckpointModal
        checkpoint={mockCheckpoint}
        isOpen={true}
        isSubmitting={false}
        onDecision={onDecision}
        onDismiss={onDismiss}
      />,
    );

    expect(screen.getByText(/review and confirm the finding/i)).toBeInTheDocument();
  });

  it("exposes action buttons with distinct names", () => {
    render(
      <HITLCheckpointModal
        checkpoint={mockCheckpoint}
        isOpen={true}
        isSubmitting={false}
        onDecision={onDecision}
        onDismiss={onDismiss}
      />,
    );

    expect(screen.getByRole("button", { name: /approve/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /terminate/i })).toBeInTheDocument();
  });

  it("invokes a decision callback when approve is pressed", () => {
    render(
      <HITLCheckpointModal
        checkpoint={mockCheckpoint}
        isOpen={true}
        isSubmitting={false}
        onDecision={onDecision}
        onDismiss={onDismiss}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    expect(onDecision).toHaveBeenCalled();
  });
});

describe("ForensicProgressOverlay accessibility", () => {
  it("renders status text for screen readers", () => {
    render(
      <ForensicProgressOverlay
        variant="council"
        title="Council deliberation"
        liveText="Compiling report"
        telemetryLabel="Arbiter telemetry"
      />,
    );

    expect(screen.getByText(/council deliberation/i)).toBeInTheDocument();
    expect(screen.getByText(/compiling report/i)).toBeInTheDocument();
  });
});
