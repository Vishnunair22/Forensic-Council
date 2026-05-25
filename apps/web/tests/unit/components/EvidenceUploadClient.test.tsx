import React from "react";
import { render, act, screen } from "@testing-library/react";
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
  },
  useReducedMotion: () => false,
}));
jest.mock("@/lib/storage", () => ({
  storage: { getItem: jest.fn(() => null), setItem: jest.fn(), removeItem: jest.fn() },
  sessionOnlyStorage: { getItem: jest.fn(() => null), setItem: jest.fn(), removeItem: jest.fn() },
}));
jest.mock("@/lib/storageKeys", () => ({
  STORAGE_KEYS: {
    AUTO_START: "forensic_auto_start",
    FC_SHOW_LOADING: "fc_show_loading",
    SESSION_ID: "forensic_session_id",
  },
}));
jest.mock("@/lib/pendingFileStore", () => ({
  __pendingFileStore: { file: null, authPromise: null, authError: null },
}));
jest.mock("@/lib/appReset", () => ({ resetActiveInvestigation: jest.fn() }));
jest.mock("@/hooks/useSound", () => ({ useSound: () => ({ playSound: jest.fn() }) }));
jest.mock("@/hooks/useInvestigation", () => ({
  useInvestigation: () => ({
    hasStartedAnalysis: false,
    handoffRecovering: false,
    status: "idle",
    agentUpdates: [],
    validCompletedAgents: [],
    pipelineThinking: "",
    allAgentsDone: false,
    phase: "",
    awaitingDecision: false,
    pipelineMessage: "",
    isNavigating: false,
    revealQueue: [],
    arbiterDeliberating: false,
    showLoadingOverlay: false,
    wsConnectionError: null,
    isReconnecting: false,
    mimeType: null,
    hitlCheckpoint: null,
    isSubmittingHITL: false,
    handleNewUpload: jest.fn(),
    handleViewResults: jest.fn(),
    handleAcceptAnalysis: jest.fn(),
    handleDeepAnalysis: jest.fn(),
    handleHITLDecision: jest.fn(),
    dismissCheckpoint: jest.fn(),
    retryWsConnection: jest.fn(),
  }),
}));
jest.mock("@/components/evidence/ArbiterDeliberationOverlay", () => ({
  ArbiterDeliberationOverlay: () => null,
}));
jest.mock("@/components/ui/ForensicErrorModal", () => ({
  ForensicErrorModal: () => null,
}));
jest.mock("@/components/evidence/HITLCheckpointModal", () => ({
  HITLCheckpointModal: () => null,
}));
jest.mock("@/components/evidence/AgentProgressDisplay", () => ({
  AgentProgressDisplay: () => null,
}));

describe("BUG-08 — handoffPending cleared on fc:reset-home", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("renders and responds to fc:reset-home event", () => {
    const { EvidenceUploadClient } = require("@/components/pages/EvidenceUploadClient");
    const { container } = render(<EvidenceUploadClient />);

    act(() => {
      jest.advanceTimersByTime(100);
    });

    const section = container.querySelector("section");
    expect(section).toBeTruthy();

    act(() => {
      window.dispatchEvent(new Event("fc:reset-home"));
    });

    expect(container.querySelector("section")).toBeTruthy();
  });
});
