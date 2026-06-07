import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
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
  isAgentSupportedForMime: (agentId: string, mimeType?: string | null) => {
    if (mimeType && mimeType.startsWith("audio/")) {
      return ["Agent2", "Agent5"].includes(agentId);
    }
    return true;
  },
  supportedAgentIdsForMime: (mimeType?: string | null) => {
    if (mimeType && mimeType.startsWith("audio/")) {
      return new Set(["Agent2", "Agent5"]);
    }
    return new Set(["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"]);
  },
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
  AgentStatusCard: (props: any) => {
    const id = props.agent?.id || props.agentId;
    const name = props.agent?.name || props.name;
    return React.createElement("div", { "data-testid": `card-${id}` }, name);
  },
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

describe("ActiveAgentsPanel default state", () => {
  it("expands the ActiveAgentsPanel by default so live agent rows are visible immediately", () => {
    render(React.createElement(AgentProgressDisplay, defaultProps));
    expect(screen.getByRole("button", { name: /Active Agents/i })).toHaveAttribute("aria-expanded", "true");
    const cards = screen.queryAllByTestId(/^card-/);
    expect(cards.length).toBeGreaterThan(0);
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
    fireEvent.click(screen.getByRole("button", { name: /Skipped Agents/i }));
    expect(screen.queryByText(/Container codec not in whitelist/)).toBeInTheDocument();
  });

  it("falls back to MIME-based reason when no backend thinking is present", () => {
    render(
      React.createElement(AgentProgressDisplay, {
        ...defaultProps,
        mimeType: "audio/mpeg",
      })
    );
    fireEvent.click(screen.getByRole("button", { name: /Skipped Agents/i }));
    expect(screen.getAllByText(/Not applicable for audio files/).length).toBeGreaterThan(0);
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
    const decisionText = container.querySelector(".fc-surface-elevated .font-semibold");
    expect(decisionText).toBeInTheDocument();
    expect(container.querySelector(".uppercase")).not.toBeInTheDocument();
    expect(container.querySelector(".tracking-widest")).not.toBeInTheDocument();
  });
});
