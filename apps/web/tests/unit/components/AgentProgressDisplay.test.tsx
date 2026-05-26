import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
  usePathname: () => "/evidence",
}));
jest.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ clear: jest.fn() }),
}));
jest.mock("framer-motion", () => ({
  motion: {
    div: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) =>
      React.createElement("div", props, children),
    span: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) =>
      React.createElement("span", props, children),
    p: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) =>
      React.createElement("p", props, children),
  },
  AnimatePresence: ({ children }: React.PropsWithChildren<Record<string, unknown>>) => React.createElement(React.Fragment, null, children),
  useReducedMotion: () => false,
}));
jest.mock("@/lib/storage", () => ({
  storage: { getItem: jest.fn(() => null), setItem: jest.fn(), removeItem: jest.fn() },
}));
jest.mock("@/lib/storageKeys", () => ({
  STORAGE_KEYS: {},
}));
jest.mock("@/lib/agentSupport", () => ({
  isAgentSupportedForMime: () => true,
  supportedAgentIdsForMime: () => new Set(["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"]),
}));
jest.mock("@/lib/agentTheme", () => ({
  accentFor: () => "blue",
}));
jest.mock("@/lib/tool-progress", () => ({
  getLiveProgressDescriptor: () => ({ label: "Running", icon: "activity" }),
}));
jest.mock("@/lib/appReset", () => ({ resetActiveInvestigation: jest.fn() }));
jest.mock("@/hooks/useSound", () => ({ useSound: () => ({ playSound: jest.fn() }) }));

jest.mock("@/lib/constants", () => ({
  AGENTS: [
    { id: "Agent1", name: "Image Forensics" },
    { id: "Agent2", name: "Audio Forensics" },
    { id: "Agent3", name: "Object Detection" },
    { id: "Agent4", name: "Video Forensics" },
    { id: "Agent5", name: "Metadata" },
  ],
}));

jest.mock("@/components/evidence/AgentStatusCard", () => ({
  AgentStatusCard: ({ agent }: { agent: { id: string; name: string } }) =>
    React.createElement("div", { "data-testid": `card-${agent.id}` }, agent.name),
  AGENT_ICONS: {},
}));

import { AgentProgressDisplay } from "@/components/evidence/AgentProgressDisplay";

const defaultProps = {
  agentUpdates: {},
  completedAgents: [],
  progressText: "Checking...",
  allAgentsDone: false,
  phase: "initial" as const,
  awaitingDecision: false,
  onNewUpload: jest.fn(),
  onViewResults: jest.fn(),
  onAcceptAnalysis: jest.fn(),
  onRunDeepAnalysis: jest.fn(),
  mimeType: "image/jpeg",
};

describe("BUG-10 — ActiveAgentsPanel collapsed by default", () => {
  it("hides agent cards when ActiveAgentsPanel is collapsed (default expanded=false)", () => {
    render(React.createElement(AgentProgressDisplay, defaultProps));
    const cards = screen.queryAllByTestId(/^card-/);
    expect(cards).toHaveLength(0);
  });
});

describe("BUG-12 — SkippedAgentsPanel surfaces backend skip reason", () => {
  it("shows backend thinking text when available for skipped agents", () => {
    render(
      React.createElement(AgentProgressDisplay, {
        ...defaultProps,
        mimeType: "video/mp4",
        agentUpdates: {
          Agent5: { status: "unsupported", thinking: "Container codec not in whitelist" },
        },
      })
    );
    expect(screen.queryByText(/Container codec not in whitelist/)).toBeInTheDocument();
  });

  it("falls back to MIME-based reason when no backend thinking is present", () => {
    render(
      React.createElement(AgentProgressDisplay, {
        ...defaultProps,
        mimeType: "audio/mpeg",
      })
    );
    expect(screen.queryByText(/Not applicable for audio files/)).toBeInTheDocument();
  });
});

describe("BUG-19 — accessibility contrast and font improvements", () => {
  it("uses fc-text-secondary (not fc-text-faint) on status text for contrast", () => {
    const { container } = render(React.createElement(AgentProgressDisplay, defaultProps));
    const statusEl = container.querySelector(".fc-text-secondary");
    expect(statusEl).toBeInTheDocument();
    expect(container.querySelector(".fc-text-faint")).not.toBeInTheDocument();
  });

  it("decision gate text does not use uppercase tracking-widest", () => {
    const { container } = render(
      React.createElement(AgentProgressDisplay, { ...defaultProps, awaitingDecision: true })
    );
    const decisionText = container.querySelector(".text-base.font-mono.font-medium");
    expect(decisionText).toBeInTheDocument();
    expect(container.querySelector(".uppercase")).not.toBeInTheDocument();
    expect(container.querySelector(".tracking-widest")).not.toBeInTheDocument();
  });
});
