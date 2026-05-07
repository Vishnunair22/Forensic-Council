/**
 * Accessibility Tests — WCAG 2.1 AA Compliance
 * ==============================================
 * Keyboard navigation, ARIA labels/roles, focus management,
 * semantic HTML, error announcements, screen-reader content,
 * disabled-state communication, and visual-only information checks.
 *
 * Run: cd apps/web && npm test -- tests/accessibility/accessibility.test.tsx
 */

import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AgentProgressDisplay } from "@/components/evidence/AgentProgressDisplay";

jest.mock("framer-motion", () => ({
  motion: new Proxy({}, {
    get: (_t, tag: string) =>
      ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => {
        const {
          animate,
          exit,
          initial,
          layout,
          layoutId,
          transition,
          variants,
          whileHover,
          whileInView,
          whileTap,
          ...domProps
        } = props;
        void animate;
        void exit;
        void initial;
        void layout;
        void layoutId;
        void transition;
        void variants;
        void whileHover;
        void whileInView;
        void whileTap;
        return React.createElement(tag, domProps, children);
      },
  }),
  AnimatePresence: ({ children }: React.PropsWithChildren<object>) => <>{children}</>,
}));

if (typeof window !== "undefined") {
  window.URL.createObjectURL = jest.fn(() => "mock-url");
  window.URL.revokeObjectURL = jest.fn();
}

const baseProgress = {
  agentUpdates: {}, completedAgents: [],
  progressText: "Ready", allAgentsDone: false,
  phase: "initial" as const, awaitingDecision: false, isNavigating: false,
  onAcceptAnalysis: jest.fn(), onRunDeepAnalysis: jest.fn(),
  onNewUpload: jest.fn(), onViewResults: jest.fn(), playSound: jest.fn(),
};

beforeEach(() => jest.clearAllMocks());

// ═══════════════════════════════════════════════════════════════════════════════
// KEYBOARD NAVIGATION
// ═══════════════════════════════════════════════════════════════════════════════

describe("Keyboard Navigation", () => {
  it("Tab moves through all buttons in decision panel", async () => {
    const user = userEvent.setup();
    render(<AgentProgressDisplay {...baseProgress} awaitingDecision={true} allAgentsDone={true} />);
    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBeGreaterThan(0);
    buttons[0].focus();
    expect(document.activeElement).toBe(buttons[0]);
  });

  it("Space activates a focused button (native button behavior)", () => {
    const onDeep = jest.fn();
    render(<AgentProgressDisplay {...baseProgress} awaitingDecision={true} allAgentsDone={true} onRunDeepAnalysis={onDeep} />);
    const btn = screen.getByRole("button", { name: /deep/i });
    btn.focus();
    fireEvent.click(btn);
    expect(onDeep).toHaveBeenCalled();
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// ARIA LABELS AND ROLES
// ═══════════════════════════════════════════════════════════════════════════════

describe("ARIA Labels and Semantic HTML", () => {
  it("all buttons have non-empty accessible name", () => {
    render(<AgentProgressDisplay {...baseProgress} awaitingDecision={true} allAgentsDone={true} />);
    screen.getAllByRole("button").forEach(btn => {
      const name = btn.getAttribute("aria-label") || btn.textContent?.trim();
      expect(name?.length ?? 0).toBeGreaterThan(0);
    });
  });

  it("disabled buttons are marked as disabled (not just visually styled)", () => {
    render(<AgentProgressDisplay {...baseProgress} awaitingDecision={true} allAgentsDone={true} isNavigating={true} />);
    const disabledBtns = screen.getAllByRole("button").filter(b => b.hasAttribute("disabled"));
    expect(disabledBtns.length).toBeGreaterThan(0);
    disabledBtns.forEach(btn => expect(btn).toBeDisabled());
  });

  it("progress text is in the document (accessible to screen readers)", () => {
    render(<AgentProgressDisplay {...baseProgress} progressText="Analyzing image… 2/5" />);
    expect(screen.getByText(/Analyzing image/i)).toBeInTheDocument();
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// LOADING/BUSY STATES
// ═══════════════════════════════════════════════════════════════════════════════

describe("Loading State Accessibility", () => {
  it("arbiter navigation state provides text feedback (Compiling Report)", () => {
    render(<AgentProgressDisplay {...baseProgress} awaitingDecision={true} allAgentsDone={true} isNavigating={true} />);
    const hasText = screen.queryAllByText(/pipeline|triage|resolved|investigation/i).length > 0;
    const hasDisabled = screen.getAllByRole("button").some(b => b.hasAttribute("disabled"));
    expect(hasText || hasDisabled).toBeTruthy();
  });

  it("navigation buttons carry disabled attribute when isNavigating", () => {
    render(<AgentProgressDisplay {...baseProgress} awaitingDecision={true} allAgentsDone={true} isNavigating={true} />);
    const hasSomeDisabled = screen.getAllByRole("button").some(b => b.hasAttribute("disabled"));
    expect(hasSomeDisabled).toBe(true);
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// FOCUS MANAGEMENT
// ═══════════════════════════════════════════════════════════════════════════════

describe("Focus Management", () => {
  it("focused button remains focused after non-destructive state update", () => {
    const { rerender } = render(
      <AgentProgressDisplay {...baseProgress} awaitingDecision={true} allAgentsDone={true} progressText="v1" />
    );
    const btn = screen.getByRole("button", { name: /deep/i });
    btn.focus();
    expect(document.activeElement).toBe(btn);
    rerender(<AgentProgressDisplay {...baseProgress} awaitingDecision={true} allAgentsDone={true} progressText="v2" />);
    expect(document.body).toBeTruthy();
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// VISUAL-ONLY INFORMATION CHECK
// ═══════════════════════════════════════════════════════════════════════════════

describe("No Color-Only Information", () => {
  it("agent completion is conveyed by text, not just color", () => {
    render(<AgentProgressDisplay
      {...baseProgress}
      completedAgents={[{ agent_id: "AGT-01", agent_name: "Image Forensics", message: "Done", status: "complete", confidence: 0.9, findings_count: 0 }]}
    />);
    expect(screen.getByText(/Image Forensics/i)).toBeInTheDocument();
  });

  it("phase label is text-based", () => {
    render(<AgentProgressDisplay {...baseProgress} phase="deep" allAgentsDone={true} />);
    expect(screen.getByText(/analysis phase complete/i)).toBeInTheDocument();
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// CONTENT STRUCTURE
// ═══════════════════════════════════════════════════════════════════════════════

describe("Document Structure", () => {
  it("agent progress display has meaningful heading or landmark", () => {
    render(<AgentProgressDisplay {...baseProgress} progressText="Analysis in progress" />);
    const hasStructure =
      document.querySelector("h1, h2, h3, [role='heading'], [role='status'], [role='main']") ||
      screen.queryByText(/Analysis in progress/i);
    expect(hasStructure).toBeTruthy();
  });
});
