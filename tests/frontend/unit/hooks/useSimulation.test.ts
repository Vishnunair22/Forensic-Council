import { renderHook, act } from "@testing-library/react";
import { useSimulation } from "@/hooks/useSimulation";
import * as api from "@/lib/api";

// ── Mocks ────────────────────────────────────────────────────────────────────

jest.mock("@/lib/api", () => ({
  ...jest.requireActual("@/lib/api"),
  createLiveSocket: jest.fn(),
}));

describe("useSimulation Hook", () => {
  const mockPlaySound = jest.fn();
  const mockOnAgentComplete = jest.fn();
  const mockOnComplete = jest.fn();

  let mockWs: any;
  let mockConnected: Promise<void>;
  let resolveConnected: () => void;
  let rejectConnected: (err: any) => void;

  beforeEach(() => {
    jest.clearAllMocks();

    mockWs = {
      send: jest.fn(),
      close: jest.fn(),
      addEventListener: jest.fn(),
      onmessage: null,
    };

    mockConnected = new Promise((resolve, reject) => {
      resolveConnected = resolve;
      rejectConnected = reject;
    });

    (api.createLiveSocket as jest.Mock).mockReturnValue({
      ws: mockWs,
      connected: mockConnected,
    });
  });

  test("initializes with idle status", () => {
    const { result } = renderHook(() => useSimulation({}));
    expect(result.current.status).toBe("idle");
    expect(result.current.completedAgents).toEqual([]);
  });

  test("connectWebSocket establishes a connection", async () => {
    const { result } = renderHook(() => useSimulation({}));
    
    let connectionPromise: Promise<void>;
    act(() => {
      connectionPromise = result.current.connectWebSocket("test-session");
    });

    expect(api.createLiveSocket).toHaveBeenCalledWith("test-session");
    
    // Simulate successful connection
    await act(async () => {
      resolveConnected();
      await connectionPromise!;
    });

    expect(result.current.status).toBe("idle"); // Status changes on AGENT_UPDATE, not just CONNECTED
  });

  test("processes AGENT_UPDATE messages", async () => {
    const { result } = renderHook(() => useSimulation({}));
    
    await act(async () => {
      resolveConnected();
      await result.current.connectWebSocket("test-session");
    });

    // Simulate AGENT_UPDATE for pipeline level
    act(() => {
      mockWs.onmessage({
        data: JSON.stringify({
          type: "AGENT_UPDATE",
          agent_id: null,
          message: "Starting analysis...",
          data: { thinking: "System is warming up" }
        })
      });
    });

    expect(result.current.status).toBe("analyzing");
    expect(result.current.pipelineMessage).toBe("Starting analysis...");
    expect(result.current.pipelineThinking).toBe("System is warming up");
  });

  test("processes AGENT_COMPLETE messages", async () => {
    const { result } = renderHook(() => useSimulation({ onAgentComplete: mockOnAgentComplete }));
    
    await act(async () => {
      resolveConnected();
      await result.current.connectWebSocket("test-session");
    });

    // Simulate AGENT_COMPLETE for AGT-01
    act(() => {
      mockWs.onmessage({
        data: JSON.stringify({
          type: "AGENT_COMPLETE",
          agent_id: "Agent1",
          agent_name: "Image Integrity",
          message: "No manipulation found",
          data: {
            confidence: 0.98,
            status: "complete",
            agent_verdict: "CLEAN"
          }
        })
      });
    });

    expect(result.current.completedAgents.length).toBe(1);
    expect(result.current.completedAgents[0].agent_id).toBe("AGT-01");
    expect(mockOnAgentComplete).toHaveBeenCalled();
  });

  test("processes HITL_CHECKPOINT messages", async () => {
    const { result } = renderHook(() => useSimulation({}));
    
    await act(async () => {
      resolveConnected();
      await result.current.connectWebSocket("test-session");
    });

    act(() => {
      mockWs.onmessage({
        data: JSON.stringify({
          type: "HITL_CHECKPOINT",
          session_id: "test-session",
          agent_id: "Agent2",
          agent_name: "Metadata Expert",
          message: "Potential spoofing detected",
          data: { checkpoint_id: "cp-123" }
        })
      });
    });

    expect(result.current.hitlCheckpoint).not.toBeNull();
    expect(result.current.hitlCheckpoint?.checkpoint_id).toBe("cp-123");
  });

  test("handles errors and sets error status", async () => {
    const { result } = renderHook(() => useSimulation({}));
    
    await act(async () => {
      resolveConnected();
      await result.current.connectWebSocket("test-session");
    });

    act(() => {
      mockWs.onmessage({
        data: JSON.stringify({
          type: "ERROR",
          message: "Backend connection lost"
        })
      });
    });

    expect(result.current.status).toBe("error");
    expect(result.current.errorMessage).toBe("Backend connection lost");
  });
});
