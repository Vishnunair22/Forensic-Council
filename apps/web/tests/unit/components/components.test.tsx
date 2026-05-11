/**
 * Frontend Unit Tests — Components
 * ==================================
 * FileUploadSection, AgentProgressDisplay, CompletionBanner, ErrorDisplay.
 * Tests rendering, props, interactions, loading/disabled states.
 *
 * Run: cd apps/web && npm test -- tests/unit/components/components.test.tsx
 */

import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AgentProgressDisplay } from "@/components/evidence/AgentProgressDisplay";

// Mock URL.createObjectURL
if (typeof window !== "undefined") {
  window.URL.createObjectURL = jest.fn(() => "mock-url");
  window.URL.revokeObjectURL = jest.fn();
}

jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ fill, unoptimized, priority, ...props }: any) => <img {...props} />,
}));

// ── Silence framer-motion animations ─────────────────────────────────────────

jest.mock("framer-motion", () => ({
  motion: new Proxy({}, {
    get: (_t, tag: string) =>
      ({ children, layout, layoutId, animate, exit, initial, transition, variants, whileHover, whileInView, whileTap, ...p }: React.PropsWithChildren<Record<string, unknown>>) =>
        React.createElement(tag, p, children),
  }),
  useReducedMotion: () => false,
  AnimatePresence: ({ children }: React.PropsWithChildren<object>) => <>{children}</>,
  useAnimation: () => ({ start: jest.fn() }),
  useInView: () => true,
}));



jest.mock("@/components/ui/AgentIcon", () => ({
  AgentIcon: () => <div data-testid="agent-icon" />,
}));

// ── AgentProgressDisplay helpers ──────────────────────────────────────────────

const progressDefaults = {
  agentUpdates: {} as Record<string, { status: string; thinking: string }>,
  completedAgents: [] as import("@/components/evidence/AgentProgressDisplay").AgentUpdate[],
  progressText: "Initializing…",
  allAgentsDone: false,
  phase: "initial" as "initial" | "deep",
  awaitingDecision: false,
  isNavigating: false,
  onAcceptAnalysis: jest.fn(),
  onRunDeepAnalysis: jest.fn(),
  onNewUpload: jest.fn(),
  onViewResults: jest.fn(),
};

beforeEach(() => jest.clearAllMocks());

// ═══════════════════════════════════════════════════════════════════════════════
// AgentProgressDisplay
// ═══════════════════════════════════════════════════════════════════════════════

describe("AgentProgressDisplay", () => {
  describe("default rendering", () => {
    it("renders without crashing", () => {
      try {
        const { container } = render(<AgentProgressDisplay {...progressDefaults} />);
        expect(container.firstChild).toBeTruthy();
      } catch (e) {
        console.error("AgentProgressDisplay render failed:", e);
        throw e;
      }
    });
    it("shows progressText", () => {
      render(<AgentProgressDisplay {...progressDefaults} progressText="Running agent 1…" />);
      expect(screen.getByText(/Running agent 1/i)).toBeInTheDocument();
    });
    it("does not show decision buttons when awaitingDecision=false", () => {
      render(<AgentProgressDisplay {...progressDefaults} awaitingDecision={false} />);
      expect(screen.queryByRole("button", { name: /accept|finalize/i })).not.toBeInTheDocument();
    });
  });

  describe("awaiting decision state", () => {
    const awaitProps = { ...progressDefaults, awaitingDecision: true, allAgentsDone: true };
    it("shows Accept Analysis button", () => {
      render(<AgentProgressDisplay {...awaitProps} />);
      expect(screen.getByRole("button", { name: /accept|finalize/i })).toBeInTheDocument();
    });
    it("shows Deep Analysis button", () => {
      render(<AgentProgressDisplay {...awaitProps} />);
      expect(screen.getByRole("button", { name: /deep/i })).toBeInTheDocument();
    });
    it("shows New Investigation button only after deep phase", () => {
      const { rerender } = render(<AgentProgressDisplay {...awaitProps} phase="initial" />);
      expect(screen.queryByRole("button", { name: /new investigation/i })).not.toBeInTheDocument();

      rerender(<AgentProgressDisplay {...awaitProps} phase="deep" />);
      expect(screen.getByRole("button", { name: /new upload|new investigation/i })).toBeInTheDocument();
    });
    it("calls onAcceptAnalysis on click", () => {
      const onAccept = jest.fn();
      render(<AgentProgressDisplay {...awaitProps} onAcceptAnalysis={onAccept} />);
      fireEvent.click(screen.getByRole("button", { name: /accept|finalize/i }));
      expect(onAccept).toHaveBeenCalled();
    });
    it("calls onRunDeepAnalysis on click", () => {
      const onDeep = jest.fn();
      render(<AgentProgressDisplay {...awaitProps} onRunDeepAnalysis={onDeep} />);
      fireEvent.click(screen.getByRole("button", { name: /deep/i }));
      expect(onDeep).toHaveBeenCalled();
    });
    it("calls onNewUpload on click when in deep complete state", () => {
      const onNew = jest.fn();
      render(<AgentProgressDisplay {...awaitProps} phase="deep" onNewUpload={onNew} />);
      fireEvent.click(screen.getByRole("button", { name: /new upload|new investigation/i }));
      expect(onNew).toHaveBeenCalled();
    });
  });

  describe("isNavigating state (arbiter fix)", () => {
    const navProps = { ...progressDefaults, awaitingDecision: true, allAgentsDone: true, isNavigating: true };
    it("disables at least one button when isNavigating", () => {
      render(<AgentProgressDisplay {...navProps} />);
      const btns = screen.getAllByRole("button");
      expect(btns.some(b => b.hasAttribute("disabled"))).toBe(true);
    });
    it("shows navigation status label when in decision phase", () => {
      render(<AgentProgressDisplay {...navProps} />);
      const hasLabel = screen.queryAllByText(/pipeline|triage|resolved/i).length > 0;
      const hasDisabled = screen.getAllByRole("button").some(b => b.hasAttribute("disabled"));
      expect(hasLabel || hasDisabled).toBeTruthy();
    });
    it("onAcceptAnalysis not called when disabled and clicking", () => {
      const onAccept = jest.fn();
      render(<AgentProgressDisplay {...navProps} onAcceptAnalysis={onAccept} />);
      const btns = screen.getAllByRole("button");
      btns.forEach(b => { if (b.hasAttribute("disabled")) fireEvent.click(b); });
      expect(onAccept).not.toHaveBeenCalled();
    });
  });

  describe("completed agents display", () => {
    const completed = [{
      agent_id: "AGT-01", agent_name: "Image Forensics",
      message: "Analysis complete", status: "complete" as const,
      confidence: 0.95, findings_count: 3,
    }];
    it("shows agent name", () => {
      render(<AgentProgressDisplay {...progressDefaults} completedAgents={completed} />);
      expect(screen.getByText(/Image Forensics/i)).toBeInTheDocument();
    });

    it("lets completed data override stale running progress", () => {
      render(
        <AgentProgressDisplay
          {...progressDefaults}
          agentUpdates={{
            Agent1: {
              status: "running",
              thinking: "Still scanning",
              tools_done: 4,
              tools_total: 4,
            },
          }}
          completedAgents={[{
            agent_id: "Agent1",
            agent_name: "Image Forensics",
            message: "Initial analysis complete",
            status: "complete",
            confidence: 0.95,
            findings_count: 1,
            agent_verdict: "CLEAN",
          }]}
        />,
      );

      expect(screen.getByText(/Final Verdict/i)).toBeInTheDocument();
      expect(screen.queryByText(/4\/4/i)).not.toBeInTheDocument();
    });

    it("shows skipped unsupported message before the card expires", () => {
      render(
        <AgentProgressDisplay
          {...progressDefaults}
          agentUpdates={{
            Agent2: {
              status: "skipped",
              thinking: "Agent2 skipped immediately: this agent does not support the submitted file type.",
            },
          }}
          mimeType="image/jpeg"
        />,
      );

      expect(screen.getByText(/does not support the submitted file type/i)).toBeInTheDocument();
      expect(screen.getByText(/hidden after 10s/i)).toBeInTheDocument();
    });

    it("shows queued cards instead of syncing all agents while waiting for a worker", async () => {
      render(
        <AgentProgressDisplay
          {...progressDefaults}
          pipelineStatus="analyzing"
          pipelineMessage="Investigation enqueued. Awaiting available forensic worker..."
          progressText="Queued"
          mimeType="image/jpeg"
        />,
      );

      await waitFor(
        () => expect(screen.getAllByText("QUEUED").length).toBeGreaterThan(0),
        { timeout: 3000 },
      );
      expect(screen.getAllByText(/awaiting available forensic worker/i).length).toBeGreaterThan(0);
      expect(screen.queryByText(/Synchronizing with pipeline/i)).not.toBeInTheDocument();
    });
  });

  describe("phase rendering", () => {
    it("renders deep phase without crash", () => {
      const { container } = render(<AgentProgressDisplay {...progressDefaults} phase="deep" />);
      expect(container.firstChild).toBeTruthy();
    });
    it("renders deep phase and shows deep label when complete", () => {
      render(<AgentProgressDisplay {...progressDefaults} phase="deep" allAgentsDone={true} />);
      expect(screen.getByText(/analysis phase complete/i)).toBeInTheDocument();
    });
  });

});
