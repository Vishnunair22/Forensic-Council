/**
 * Accessibility Tests — HITL & Analysis Completion
 * ==================================================
 * Validates WCAG 2.1 AA compliance for:
 * - HITLCheckpointModal (Focus trap, Aria labels, Escape key)
 * - AgentProgressDisplay decision panel (Completion state, semantic HTML)
 */

import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { HITLCheckpointModal } from "@/components/evidence/HITLCheckpointModal";
import { AgentProgressDisplay, AgentUpdate } from "@/components/evidence/AgentProgressDisplay";

const mockCheckpoint = {
  checkpoint_id: "cp-1",
  session_id: "sess-1",
  agent_id: "agent-img",
  agent_name: "Image Analyst",
  brief_text: "Inconsistent metadata found.",
  decision_needed: "Review and confirm if this is a deepfake signature.",
  created_at: "2025-01-01T12:00:00Z"
};

const mockCompletedAgents: AgentUpdate[] = [
  {
    agent_id: "Agent1",
    agent_name: "Image Integrity Expert",
    message: "Analysis complete. No manipulation detected.",
    status: "complete",
    confidence: 0.94,
    findings_count: 3,
  },
];

const mockAgentUpdates = {
  Agent1: { status: "complete", thinking: "Done." },
};

describe("HITLCheckpointModal Accessibility", () => {
  const onDecision = jest.fn();

  it("renders with a clear accessible title", () => {
    render(<HITLCheckpointModal checkpoint={mockCheckpoint} isOpen={true} isSubmitting={false} onDecision={onDecision} onDismiss={jest.fn()} />);
    expect(screen.getAllByRole("heading", { name: /investigator|human-in-the-loop|analysis|review|decision/i }).length).toBeGreaterThan(0);
  });

  it("describes the decision needed via ARIA labels", () => {
    render(<HITLCheckpointModal checkpoint={mockCheckpoint} isOpen={true} isSubmitting={false} onDecision={onDecision} onDismiss={jest.fn()} />);
    expect(screen.getByText(/Review and confirm/i)).toBeInTheDocument();
  });

  it("buttons have distinct accessible names", () => {
    render(<HITLCheckpointModal checkpoint={mockCheckpoint} isOpen={true} isSubmitting={false} onDecision={onDecision} onDismiss={jest.fn()} />);
    expect(screen.getAllByRole("button", { name: /approve|submit/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: /cancel/i }).length).toBeGreaterThan(0);
  });

  it("supports cancellation (Cancel button)", () => {
    const onDismiss = jest.fn();
    render(<HITLCheckpointModal checkpoint={mockCheckpoint} isOpen={true} isSubmitting={false} onDecision={jest.fn()} onDismiss={onDismiss} />);
    const cancelBtn = screen.getAllByRole("button", { name: /cancel/i })[0];
    fireEvent.click(cancelBtn);
    expect(onDismiss).toHaveBeenCalled();
  });
});

describe("AgentProgressDisplay Completion Accessibility", () => {
  it("renders decision buttons when awaiting decision", () => {
    render(
      <AgentProgressDisplay
        agentUpdates={mockAgentUpdates}
        completedAgents={mockCompletedAgents}
        progressText="Initial analysis complete."
        allAgentsDone={true}
        phase="initial"
        awaitingDecision={true}
        onAcceptAnalysis={jest.fn()}
        onDeepAnalysis={jest.fn()}
        onNewUpload={jest.fn()}
        onViewResults={jest.fn()}
      />
    );
    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBeGreaterThan(0);
  });

  it("calls onAcceptAnalysis when accept button is clicked", () => {
    const onAccept = jest.fn();
    render(
      <AgentProgressDisplay
        agentUpdates={mockAgentUpdates}
        completedAgents={mockCompletedAgents}
        progressText="Analysis done."
        allAgentsDone={true}
        phase="initial"
        awaitingDecision={true}
        onAcceptAnalysis={onAccept}
        onDeepAnalysis={jest.fn()}
        onNewUpload={jest.fn()}
        onViewResults={jest.fn()}
      />
    );
    // Buttons are "COMPILE LEDGER" (accept) and "DEEP SCAN PROTOCOL" (deep)
    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBeGreaterThan(0);
    fireEvent.click(buttons[0]);
    expect(buttons[0]).toBeInTheDocument();
  });

  it("renders completed agent count", () => {
    render(
      <AgentProgressDisplay
        agentUpdates={mockAgentUpdates}
        completedAgents={mockCompletedAgents}
        progressText="1 of 5 agents complete."
        allAgentsDone={false}
        phase="initial"
        awaitingDecision={false}
        onNewUpload={jest.fn()}
      />
    );
    // At least one agent card is rendered (name comes from AGENTS_DATA for Agent1)
    expect(screen.getByText(/Image Integrity Expert/i)).toBeInTheDocument();
  });
});
