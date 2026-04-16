import { renderHook, act } from "@testing-library/react";
import { useInvestigation } from "@/hooks/useInvestigation";
import * as api from "@/lib/api";
import { useSimulation } from "@/hooks/useSimulation";
import { useRouter } from "next/navigation";

// ── Mocks ────────────────────────────────────────────────────────────────────

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

// Mock URL.createObjectURL
if (typeof window !== "undefined") {
  window.URL.createObjectURL = jest.fn(() => "mock-url");
  window.URL.revokeObjectURL = jest.fn();
}

describe("useInvestigation Hook", () => {
  const mockPlaySound = jest.fn();
  const mockPush = jest.fn();
  const mockConnectWebSocket = jest.fn().mockResolvedValue(undefined);
  const mockResetSimulation = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    (useRouter as jest.Mock).mockReturnValue({ push: mockPush });
    
    (useSimulation as jest.Mock).mockReturnValue({
      status: "idle",
      agentUpdates: {},
      completedAgents: [],
      pipelineMessage: "",
      pipelineThinking: "",
      hitlCheckpoint: null,
      errorMessage: null,
      connectWebSocket: mockConnectWebSocket,
      resetSimulation: mockResetSimulation,
      startSimulation: jest.fn(),
    });

    (api.autoLoginAsInvestigator as jest.Mock).mockResolvedValue({ access_token: "test-token" });
    
    // Mock sessionStorage
    const store: Record<string, string> = {};
    Object.defineProperty(window, "sessionStorage", {
      value: {
        getItem: (key: string) => store[key] || null,
        setItem: (key: string, value: string) => { store[key] = value; },
        removeItem: (key: string) => { delete store[key]; },
        clear: () => { for (const key in store) delete store[key]; },
      },
      writable: true,
    });
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

    // Test invalid extension
    const invalidFile = new File([""], "test.txt", { type: "text/plain" });
    act(() => {
      result.current.handleFile(invalidFile);
    });
    expect(result.current.validationError).toContain("Invalid file format");
    expect(result.current.file).toBeNull();

    // Test valid file
    const validFile = new File([""], "test.jpg", { type: "image/jpeg" });
    act(() => {
      result.current.handleFile(validFile);
    });
    expect(result.current.file).toBe(validFile);
    expect(result.current.validationError).toBeNull();
  });

  test("triggerAnalysis starts the investigation flow", async () => {
    const validFile = new File([""], "test.jpg", { type: "image/jpeg" });
    const mockSessionId = "mock-session-123";
    (api.startInvestigation as jest.Mock).mockResolvedValue({ session_id: mockSessionId });

    const { result } = renderHook(() => useInvestigation(mockPlaySound));

    await act(async () => {
      await result.current.triggerAnalysis(validFile);
    });

    expect(api.startInvestigation).toHaveBeenCalled();
    expect(mockConnectWebSocket).toHaveBeenCalledWith(mockSessionId);
    expect(result.current.hasStartedAnalysis).toBe(true);
    expect(result.current.showUploadForm).toBe(false);
    expect(mockPlaySound).toHaveBeenCalledWith("upload");
  });

  test("handleNewUpload resets the state", () => {
    const { result } = renderHook(() => useInvestigation(mockPlaySound));

    act(() => {
      result.current.handleNewUpload();
    });

    expect(mockResetSimulation).toHaveBeenCalled();
    expect(result.current.file).toBeNull();
    expect(result.current.hasStartedAnalysis).toBe(false);
    expect(result.current.showUploadForm).toBe(true);
  });
});
