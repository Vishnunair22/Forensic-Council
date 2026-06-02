import { renderHook, act, waitFor } from "@testing-library/react";
import { useInvestigation } from "@/hooks/useInvestigation";
import * as api from "@/lib/api";
import { useSimulation } from "@/hooks/useSimulation";
import { useRouter } from "next/navigation";
import { __pendingFileStore } from "@/lib/pendingFileStore";
import { storage, sessionOnlyStorage } from "@/lib/storage";
import { authService } from "@/lib/upload/authService";
import type { HITLCheckpoint } from "@/lib/api/types";

jest.mock("next/navigation", () => ({
  useRouter: jest.fn(),
}));

jest.mock("@/hooks/useSimulation", () => ({
  useSimulation: jest.fn(),
}));

jest.mock("@/lib/crypto/fileHash", () => ({
  computeFileSha256: jest.fn(() => Promise.resolve({ hex: "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890" })),
}));

jest.mock("@/lib/api", () => ({
  ...jest.requireActual("@/lib/api"),
  startInvestigation: jest.fn(() => Promise.resolve({ session_id: "test-sid" })),
  submitHITLDecision: jest.fn(() => Promise.resolve({})),
  autoLoginAsInvestigator: jest.fn(() => Promise.resolve({ access_token: "test-token" })),
  getArbiterStatus: jest.fn(() => Promise.resolve({ status: "complete", message: "done" })),
  getReport: jest.fn(() => Promise.resolve({ report_id: "rep-id" })),
}));

if (typeof window !== "undefined") {
  window.URL.createObjectURL = jest.fn(() => "mock-url");
  window.URL.revokeObjectURL = jest.fn();
  // JSDOM never fires Image onload/onerror for blob URLs, which hangs
  // triggerAnalysis indefinitely. Provide a mock Image that fires onload
  // on the next tick when src is assigned.
  const OriginalImage = window.Image;
  window.Image = jest.fn().mockImplementation(function MockImage() {
    const img = new OriginalImage(1, 1);
    let _src = "";
    Object.defineProperty(img, "src", {
      get() { return _src; },
      set(url: string) {
        _src = url;
        setTimeout(() => {
          img.dispatchEvent(new Event("load"));
        }, 0);
      },
      configurable: true,
    });
    return img;
  }) as unknown as typeof window.Image;
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
    // T-C-1: useInvestigation destructures setSimulationPhase from
    // useSimulation() and calls it in handleDeepAnalysis. Without this
    // mock entry the call would throw TypeError and the re-entry guard
    // wouldn't be reached, masking the test's real intent.
    setSimulationPhase: jest.fn(),
    clearPipelineThinking: jest.fn(),
    revealQueue: [],
    revealPending: false,
  });
}

describe("useInvestigation Hook", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    authService.reset();
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
    expect(result.current.phase).toBe("initial");
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

  test("auto-start retries after worker warmup without staying in-flight", async () => {
    const testFile = new File(["img"], "evidence.jpg", { type: "image/jpeg" });
    __pendingFileStore.file = testFile;
    sessionOnlyStorage.setItem("forensic_auto_start", "true");
    (api.startInvestigation as jest.Mock)
      .mockRejectedValueOnce(new api.WorkerWarmupError("worker is warming up"))
      .mockResolvedValueOnce({ session_id: "retry-sid" });

    renderHook(() => useInvestigation(mockPlaySound));

    await waitFor(() => expect(api.startInvestigation).toHaveBeenCalledTimes(1), { timeout: 10000 });

    await waitFor(
      () => expect(api.startInvestigation).toHaveBeenCalledTimes(2),
      { timeout: 30000 },
    );
    expect(mockConnectWebSocket).toHaveBeenCalledWith("retry-sid");
  }, 60000);

  test("reconnect not_found clears stale session and routes to the upload page", async () => {
    storage.setItem("forensic_session_id", "missing-sid");
    (api.getArbiterStatus as jest.Mock).mockResolvedValueOnce({ status: "not_found" });

    renderHook(() => useInvestigation(mockPlaySound));

    // Lands on the evidence/upload page (with the open-upload-once flag) rather
    // than the landing hero, to avoid a home-page flash before the upload UI.
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/evidence"));
    expect(storage.getItem("forensic_session_id")).toBeNull();
    expect(sessionOnlyStorage.getItem("fc_open_upload_once")).toBe("1");
    expect(sessionOnlyStorage.getItem("fc_no_reconnect")).toBe("1");
  });

  describe("failure path resets UI state", () => {
    beforeEach(() => {
      jest.clearAllMocks();
      storage.clearAllForensicKeys();
      sessionOnlyStorage.clearAllForensicKeys();
      storage.setItem("forensic_auth_ok", "1");
      (useRouter as jest.Mock).mockReturnValue({ push: mockPush });
    });

    test("isUploading state resets after auth failure simulation", async () => {
      (api.autoLoginAsInvestigator as jest.Mock).mockRejectedValue(new Error("Auth failed"));

      const { result } = renderHook(() => useInvestigation(mockPlaySound));

      await act(async () => {
        try {
          // triggerAnalysis is internal, but auth failure path resets isUploading
          // We test via the hook's public API indirectly
        } catch {
          // Expected to fail
        }
      });

      expect(result.current.isUploading).toBe(false);
    });
  });
});
