import { renderHook, act, waitFor } from "@testing-library/react";
import { useInvestigation } from "@/hooks/useInvestigation";
import * as api from "@/lib/api";
import { useSimulation } from "@/hooks/useSimulation";
import { useRouter } from "next/navigation";
import { __pendingFileStore } from "@/lib/pendingFileStore";
import { storage, sessionOnlyStorage } from "@/lib/storage";
import type { HITLCheckpoint } from "@/lib/api/types";

jest.mock("next/navigation", () => ({
  useRouter: jest.fn(),
}));

jest.mock("@/hooks/useSimulation", () => ({
  useSimulation: jest.fn(),
}));

jest.mock("@/lib/api", () => ({
  ...jest.requireActual("@/lib/api"),
  startInvestigation: jest.fn(),
  submitHITLDecision: jest.fn(),
  autoLoginAsInvestigator: jest.fn(),
  getArbiterStatus: jest.fn(),
  getReport: jest.fn(),
}));

if (typeof window !== "undefined") {
  window.URL.createObjectURL = jest.fn(() => "mock-url");
  window.URL.revokeObjectURL = jest.fn();
}

const mockPlaySound = jest.fn();
const mockPush = jest.fn();
const mockConnectWebSocket = jest.fn().mockResolvedValue(undefined);
const mockResetSimulation = jest.fn();
const mockStartSimulation = jest.fn();
const mockRestoreSimulationState = jest.fn();
const mockResumeInvestigation = jest.fn().mockResolvedValue(undefined);

function setupSimulationMock(
  initialStatus = "idle",
  hitl: HITLCheckpoint | null = null,
) {
  (useSimulation as jest.Mock).mockReturnValue({
    status: initialStatus,
    agentUpdates: {},
    completedAgents: [],
    pipelineMessage: "",
    pipelineThinking: "",
    hitlCheckpoint: hitl,
    errorMessage: null,
    connectWebSocket: mockConnectWebSocket,
    resetSimulation: mockResetSimulation,
    startSimulation: mockStartSimulation,
    resumeInvestigation: mockResumeInvestigation,
    dismissCheckpoint: jest.fn(),
    clearCompletedAgents: jest.fn(),
    restoreSimulationState: mockRestoreSimulationState,
    isReconnecting: false,
    arbiterStatus: null,
    arbiterThinking: null,
  });
}

describe("useInvestigation Hook", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    storage.clearAllForensicKeys();
    sessionOnlyStorage.clearAllForensicKeys();
    storage.setItem("forensic_auth_ok", "1");
    (useRouter as jest.Mock).mockReturnValue({ push: mockPush });
    setupSimulationMock("idle");
    (api.autoLoginAsInvestigator as jest.Mock).mockResolvedValue({ access_token: "test-token" });
    (api.startInvestigation as jest.Mock).mockReset();
    __pendingFileStore.file = null;
    __pendingFileStore.authPromise = null;
  });

  test("initializes with default state", () => {
    const { result } = renderHook(() => useInvestigation(mockPlaySound));
    expect(result.current.file).toBeNull();
    expect(result.current.phase).toBe("initial");
  });

  test("handleFile sets the file or validation error", () => {
    const { result } = renderHook(() => useInvestigation(mockPlaySound));
    const testFile = new File([""], "test.jpg", { type: "image/jpeg" });
    act(() => { result.current.handleFile(testFile); });
    expect(result.current.file).toBe(testFile);
  });

  test("handleNewUpload calls reset and routes home", () => {
    const { result } = renderHook(() => useInvestigation(mockPlaySound));
    act(() => { result.current.handleNewUpload(); });
    expect(mockResetSimulation).toHaveBeenCalled();
    expect(mockPush).toHaveBeenCalledWith("/?upload=1");
  });

  test("handleAcceptAnalysis guards against re-entry", async () => {
    storage.setItem("forensic_session_id", "test-sid");
    const { result } = renderHook(() => useInvestigation(mockPlaySound));
    
    await act(async () => {
      const p = result.current.handleAcceptAnalysis();
      await result.current.handleAcceptAnalysis(); // concurrent call
      await p;
    });

    expect(mockResumeInvestigation).toHaveBeenCalledTimes(1);
  });

  test("handleDeepAnalysis prevents re-entry", async () => {
    storage.setItem("forensic_session_id", "test-sid");
    const { result } = renderHook(() => useInvestigation(mockPlaySound));
    
    await act(async () => {
      const p1 = result.current.handleDeepAnalysis();
      await result.current.handleDeepAnalysis(); // concurrent call
      await p1;
    });

    expect(mockResumeInvestigation).toHaveBeenCalledTimes(1);
  });

  test("handleHITLDecision calls API and dismisses checkpoint", async () => {
    const checkpoint = {
      session_id: "sid",
      checkpoint_id: "cp",
      agent_id: "agent1",
      agent_name: "Agent 1",
      brief_text: "test",
      decision_needed: "APPROVE",
      created_at: new Date().toISOString(),
    };
    setupSimulationMock("awaiting_decision", checkpoint);
    
    const { result } = renderHook(() => useInvestigation(mockPlaySound));
    (api.submitHITLDecision as jest.Mock).mockResolvedValue({});

    await act(async () => {
      await result.current.handleHITLDecision("APPROVE", "looks good");
    });

    expect(api.submitHITLDecision).toHaveBeenCalled();
  });
});
