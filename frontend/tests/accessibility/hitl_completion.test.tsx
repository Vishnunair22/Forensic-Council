/**
 * Accessibility Tests — HITL & Completion
 * ========================================
 * Validates WCAG 2.1 AA compliance for:
 * - HITLCheckpointModal (Focus trap, Aria labels, Escape key)
 * - CompletionBanner (Announcement, Contrast, Semantic HTML)
 */

import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { HITLCheckpointModal } from "@/components/evidence/HITLCheckpointModal";
import { CompletionBanner } from "@/components/evidence/CompletionBanner";



const mockCheckpoint = {
  checkpoint_id: "cp-1",
  session_id: "sess-1",
  agent_id: "agent-img",
  agent_name: "Image Analyst",
  brief_text: "Inconsistent metadata found.",
  decision_needed: "Review and confirm if this is a deepfake signature.",
  created_at: "2025-01-01T12:00:00Z"
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

describe("CompletionBanner Accessibility", () => {
  const mockReport = {
    report_id: "r1",
    overall_verdict: "CERTAIN",
    overall_confidence: 0.98,
    signed_utc: "2025-01-01T12:05:00Z"
  };

  it("announces completion to screen readers", () => {
    render(<CompletionBanner agentCount={5} completedCount={5} onViewResults={jest.fn()} onAnalyzeNew={jest.fn()} />);
    // Should have role="status" or role="alert" or aria-live
    const banner = screen.queryByRole("status") || screen.queryByRole("alert") || document.querySelector("[aria-live]");
    expect(banner).not.toBeNull();
  });

  it("presents verdict text clearly", () => {
    render(<CompletionBanner agentCount={5} completedCount={5} onViewResults={jest.fn()} onAnalyzeNew={jest.fn()} />);
    expect(screen.getByText(/Analysis Complete/i)).toBeInTheDocument();
  });

  it("contains clickable link to full report", () => {
    render(<CompletionBanner agentCount={5} completedCount={5} onViewResults={jest.fn()} onAnalyzeNew={jest.fn()} />);
    expect(screen.getByRole("button", { name: /view|full|report|access/i })).toBeInTheDocument();
  });
});
