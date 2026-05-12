import { renderHook, act, waitFor } from "@testing-library/react";
import { useInvestigation } from "@/hooks/useInvestigation";
import * as api from "@/lib/api";
import { useSimulation } from "@/hooks/useSimulation";
import { useRouter } from "next/navigation";

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

function setupMockStorage() {
  const store: Record<string, string> = { forensic_auth_ok: "1" };
  Object.defineProperty(window, "sessionStorage", {
    value: {
      getItem: (key: string) => store[key] || null,
      setItem: (key: string, value: string) => { store[key] = value; },
      removeItem: (key: string) => { delete store[key]; },
      clear: () => { for (const key in store) delete store[key]; },
    },
    writable: true,
  });
  Object.defineProperty(window, "localStorage", {
    value: {
      getItem: (key: string) => store[key] || null,
      setItem: (key: string, value: string) => { store[key] = value; },
      removeItem: (key: string) => { delete store[key]; },
      clear: () => { for (const key in store) delete store[key]; },
    },
    writable: true,
  });
}

function setupSimulationMock(initialStatus = "idle") {
  (useSimulation as jest.Mock).mockReturnValue({
    status: initialStatus,
    agentUpdates: {},
    completedAgents: [],
    pipelineMessage: "",
    pipelineThinking: "",
    hitlCheckpoint: null,
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
    setupMockStorage();
    (useRouter as jest.Mock).mockReturnValue({ push: mockPush });
    setupSimulationMock("idle");
    (api.autoLoginAsInvestigator as jest.Mock).mockResolvedValue({ access_token: "test-token" });
    (api.startInvestigation as jest.Mock).mockReset();
  });

  test("initializes with default state", () => {
    const { result } = renderHook(() => useInvestigation(mockPlaySound));

    expect(result.current.file).toBeNull();
    expect(result.current.phase).toBe("initial");
    expect(result.current.hasStartedAnalysis).toBe(false);
    expect(result.current.showUploadForm).toBe(true);
  });

  test("handleFile sets the file or validation error", () => {
    const { result } = renderHook(() => useInvestigation(mockPlaySound));

    const invalidFile = new File([""], "test.txt", { type: "text/plain" });
    act(() => {
      result.current.handleFile(invalidFile);
    });
    expect(result.current.validationError).toMatch(/not supported|unsupported|invalid/i);
    expect(result.current.file).toBeNull();

    const validFile = new File([""], "test.jpg", { type: "image/jpeg" });
    act(() => {
      result.current.handleFile(validFile);
    });
    expect(result.current.file).toBe(validFile);
    expect(result.current.validationError).toBeNull();
  });

  test("handleNewUpload calls reset and routes home", () => {
    const { result } = renderHook(() => useInvestigation(mockPlaySound));

    act(() => {
      result.current.handleNewUpload();
    });

    expect(mockPush).toHaveBeenCalledWith("/?upload=1");
  });

  test("handleAcceptAnalysis guards against re-entry via isNavigating", () => {
    const { result } = renderHook(() => useInvestigation(mockPlaySound));

    act(() => {
      result.current.handleNewUpload();
    });

    const { result: result2 } = renderHook(() => useInvestigation(mockPlaySound));
    act(() => {
      result2.current.handleNewUpload();
    });

    expect(mockPush).toHaveBeenCalledTimes(2);
  });

  test("triggerAnalysis guards against concurrent calls via investigationInFlightRef", () => {
    (api.startInvestigation as jest.Mock).mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve({ session_id: "sid-1" }), 5000)),
    );

    const { result } = renderHook(() => useInvestigation(mockPlaySound));
    const validFile = new File([""], "test.jpg", { type: "image/jpeg" });

    act(() => {
      result.current.handleFile(validFile);
    });

    expect(mockPush).not.toHaveBeenCalled();
  });

  test("duplicate upload reconnect path is guarded", async () => {
    const existingSid = "00000000-0000-4000-8000-000000000001";
    (api.startInvestigation as jest.Mock).mockRejectedValue(
      new (class extends Error {
        existingSessionId = existingSid;
        name = "DuplicateInvestigationError";
      })("Duplicate detected"),
    );

    const { result } = renderHook(() => useInvestigation(mockPlaySound));
    const validFile = new File([""], "test.jpg", { type: "image/jpeg" });

    act(() => {
      result.current.handleFile(validFile);
    });

    await waitFor(
      () => {
        expect(mockConnectWebSocket).toHaveBeenCalledWith(existingSid, true);
      },
      { timeout: 5000 },
    );
  });

  test("pending file in store triggers auto-start on mount", async () => {
    (api.startInvestigation as jest.Mock).mockResolvedValue({ session_id: "sid-auto" });

    const { __pendingFileStore } = await import("@/lib/pendingFileStore");
    const testFile = new File([""], "auto.jpg", { type: "image/jpeg" });
    __pendingFileStore.file = testFile;

    const { result: result2 } = renderHook(() => useInvestigation(mockPlaySound));

    await waitFor(
      () => {
        expect(api.startInvestigation).toHaveBeenCalled();
      },
      { timeout: 5000 },
    );

    __pendingFileStore.file = null;
  });

  test("handleDeepAnalysis prevents re-entry while investigationInFlightRef is set", () => {
    const { result } = renderHook(() => useInvestigation(mockPlaySound));

    (api.getArbiterStatus as jest.Mock).mockResolvedValue({ status: "running" });

    act(() => {
      result.current.handleDeepAnalysis();
    });

    act(() => {
      result.current.handleDeepAnalysis();
    });

    expect(mockResumeInvestigation).toHaveBeenCalledTimes(1);
  });

  test("handleHITLDecision calls API and dismisses checkpoint", async () => {
    (api.submitHITLDecision as jest.Mock).mockResolvedValue(undefined);

    setupSimulationMock("analyzing");
    const { useSimulation: useSim } = jest.requireMock("@/hooks/useSimulation");
    useSim.mockReturnValue({
      ...useSim(),
      hitlCheckpoint: {
        checkpoint_id: "cp-1",
        session_id: "sid-1",
        agent_id: "Agent1",
        agent_name: "Image Forensics",
        brief_text: "Test checkpoint",
        decision_needed: "APPROVE, REDIRECT, or TERMINATE",
        created_at: new Date().toISOString(),
      },
    });

    const { result } = renderHook(() => useInvestigation(mockPlaySound));

    await act(
      async () => {
        await result.current.handleHITLDecision("APPROVE", "Looks good");
      },
    );

    expect(api.submitHITLDecision).toHaveBeenCalledWith(
      expect.objectContaining({
        decision: "APPROVE",
        note: "Looks good",
        checkpoint_id: "cp-1",
        agent_id: "Agent1",
        session_id: "sid-1",
      }),
    );
  });
});
