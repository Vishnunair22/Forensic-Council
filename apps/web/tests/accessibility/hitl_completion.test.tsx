import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { HITLCheckpointModal } from "@/components/evidence/HITLCheckpointModal";
import { ForensicProgressOverlay } from "@/components/ui/ForensicProgressOverlay";

jest.mock("framer-motion", () => ({
  motion: new Proxy({}, {
    get: (_t: any, tag: string) =>
      ({ children, layout, layoutId, animate, exit, initial, transition, variants, whileHover, whileInView, whileTap, ...p }: React.PropsWithChildren<Record<string, unknown>>) =>
        React.createElement(tag, p, children),
  }),
  AnimatePresence: ({ children }: React.PropsWithChildren<object>) => <>{children}</>,
}));

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
      screen.getByRole("heading", { name: /investigator intervention/i }),
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

  it("exposes action choices as an accessible radio group", () => {
    render(
      <HITLCheckpointModal
        checkpoint={mockCheckpoint}
        isOpen={true}
        isSubmitting={false}
        onDecision={onDecision}
        onDismiss={onDismiss}
      />,
    );

    expect(screen.getByRole("radiogroup", { name: /protocol selection/i })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /approve/i })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /escalate/i })).toBeInTheDocument();
  });

  it("selects approve and invokes decision callback on finalize", async () => {
    render(
      <HITLCheckpointModal
        checkpoint={mockCheckpoint}
        isOpen={true}
        isSubmitting={false}
        onDecision={onDecision}
        onDismiss={onDismiss}
      />,
    );

    fireEvent.click(screen.getByRole("radio", { name: /approve/i }));
    fireEvent.click(screen.getByRole("button", { name: /finalize decision/i }));
    expect(onDecision).toHaveBeenCalledWith("APPROVE", "");
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
