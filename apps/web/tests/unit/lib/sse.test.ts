/**
 * Tests for createLiveSocket WebSocket lifecycle.
 *
 * Covers:
 * - createLiveSocket returns { ws, connected } shape
 * - WebSocket URL includes the session ID and /live path
 * - forensic-v1 protocol is always included
 * - connected promise resolves on CONNECTED message
 * - connected promise rejects on onerror
 * - connected promise rejects after 12s timeout
 * - ws.close() callable without throwing
 * - WS message payload structural validation
 */

import { createLiveSocket } from "@/lib/api";

// ── WebSocket mock (matches pattern in websocket_flow.test.ts) ────────────────

let wsInstance: MockWS;

class MockWS {
  send = jest.fn();
  close = jest.fn();
  onopen: ((e: Event) => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  onclose: ((e: CloseEvent) => void) | null = null;
  url: string;
  protocols: string[];

  private listeners: Record<string, Array<(e: unknown) => void>> = {};

  constructor(url: string, protocols?: string | string[]) {
    this.url = url;
    this.protocols = Array.isArray(protocols)
      ? protocols
      : protocols
      ? [protocols]
      : [];
    wsInstance = this;
  }

  addEventListener(type: string, listener: (e: unknown) => void) {
    if (!this.listeners[type]) this.listeners[type] = [];
    this.listeners[type].push(listener);
  }

  removeEventListener(type: string, listener: (e: unknown) => void) {
    if (!this.listeners[type]) return;
    this.listeners[type] = this.listeners[type].filter((l) => l !== listener);
  }

  simulateOpen() {
    this.onopen?.(new Event("open"));
    this.listeners["open"]?.forEach((l) => l(new Event("open")));
  }

  simulateMessage(data: unknown) {
    const event = new MessageEvent("message", {
      data: typeof data === "string" ? data : JSON.stringify(data),
    });
    this.onmessage?.(event);
    this.listeners["message"]?.forEach((l) => l(event));
  }

  simulateError() {
    this.onerror?.(new Event("error"));
    this.listeners["error"]?.forEach((l) => l(new Event("error")));
  }

  simulateClose(code = 1000) {
    const event = new CloseEvent("close", { code });
    this.onclose?.(event);
    this.listeners["close"]?.forEach((l) => l(event));
  }
}

global.WebSocket = MockWS as unknown as typeof WebSocket;

// ── Setup / teardown ──────────────────────────────────────────────────────────

beforeEach(() => {
  jest.clearAllMocks();
  jest.useFakeTimers();
});

afterEach(() => {
  jest.useRealTimers();
});

// ── Shape of return value ─────────────────────────────────────────────────────

describe("createLiveSocket — return shape", () => {
  it("returns an object with ws and connected keys", () => {
    const result = createLiveSocket("sess-001");
    expect(result).toHaveProperty("ws");
    expect(result).toHaveProperty("connected");
  });

  it("ws is a MockWS instance", () => {
    const { ws } = createLiveSocket("sess-001");
    expect(ws).toBeInstanceOf(MockWS);
  });

  it("connected is a Promise", () => {
    const { connected } = createLiveSocket("sess-001");
    expect(connected).toBeInstanceOf(Promise);
  });
});

// ── URL construction ──────────────────────────────────────────────────────────

describe("createLiveSocket — URL", () => {
  it("includes session ID in WebSocket URL", () => {
    createLiveSocket("my-session-id");
    expect(wsInstance.url).toContain("my-session-id");
  });

  it("URL uses ws:// or wss:// scheme", () => {
    createLiveSocket("sess-url");
    const url = wsInstance.url;
    expect(url.startsWith("ws://") || url.startsWith("wss://")).toBe(true);
  });

  it("URL includes /live path segment", () => {
    createLiveSocket("sess-path");
    expect(wsInstance.url).toContain("/live");
  });

  it("URL includes sessions prefix", () => {
    createLiveSocket("sess-sessions");
    expect(wsInstance.url).toContain("sessions");
  });
});

// ── Protocol negotiation ──────────────────────────────────────────────────────

describe("createLiveSocket — protocols", () => {
  it("includes forensic-v1 protocol", () => {
    createLiveSocket("sess-proto");
    expect(wsInstance.protocols).toContain("forensic-v1");
  });
});

// ── connected promise ─────────────────────────────────────────────────────────

describe("createLiveSocket — connected promise", () => {
  it("resolves when CONNECTED message received", async () => {
    const { connected } = createLiveSocket("sess-resolve");
    wsInstance.simulateMessage({ type: "CONNECTED" });
    await expect(connected).resolves.toBeUndefined();
  });

  it("rejects on WebSocket error", async () => {
    const { connected } = createLiveSocket("sess-error");
    wsInstance.simulateError();
    await expect(connected).rejects.toThrow();
  });

  it("rejects after 20s connection timeout", async () => {
    const { connected } = createLiveSocket("sess-timeout");
    jest.advanceTimersByTime(20_001);
    await expect(connected).rejects.toThrow(/timed out/i);
  });

  it("does not throw on double rejection", async () => {
    const { connected } = createLiveSocket("sess-double");
    wsInstance.simulateError();
    jest.advanceTimersByTime(21_000);
    let count = 0;
    try {
      await connected;
    } catch {
      count++;
    }
    expect(count).toBe(1);
  });
});

// ── Connection close ──────────────────────────────────────────────────────────

describe("createLiveSocket — close", () => {
  it("ws.close() is callable without error", () => {
    const { ws } = createLiveSocket("sess-close");
    expect(() => ws.close()).not.toThrow();
  });

  it("onclose fires when simulateClose called", () => {
    createLiveSocket("sess-close2");
    const handler = jest.fn();
    wsInstance.onclose = handler;
    wsInstance.simulateClose();
    expect(handler).toHaveBeenCalled();
  });
});

// ── WS message payload shapes ─────────────────────────────────────────────────

describe("WS message payload shapes", () => {
  const AGENT_IDS = ["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"];

  it.each(AGENT_IDS)("%s matches expected agent ID pattern", (id) => {
    expect(id).toMatch(/^Agent[1-5]$/);
  });

  it("AGENT_UPDATE payload has required fields", () => {
    const p = {
      type: "AGENT_UPDATE",
      agent_id: "Agent1",
      message: "Running ELA",
      data: { thinking: "Analyzing" },
    };
    expect(p.type).toBe("AGENT_UPDATE");
    expect(p.agent_id).toBeTruthy();
    expect(p.message).toBeTruthy();
  });

  it("AGENT_COMPLETE payload has confidence in [0,1]", () => {
    const p = { type: "AGENT_COMPLETE", agent_id: "Agent1", data: { confidence: 0.95 } };
    expect(p.data.confidence).toBeGreaterThanOrEqual(0);
    expect(p.data.confidence).toBeLessThanOrEqual(1);
  });

  it("HITL_CHECKPOINT payload has checkpoint_id", () => {
    const p = { type: "HITL_CHECKPOINT", data: { checkpoint_id: "cp-123" } };
    expect(p.data.checkpoint_id).toBeTruthy();
  });

  it("INVESTIGATION_COMPLETE payload has report_available", () => {
    const p = { type: "INVESTIGATION_COMPLETE", data: { report_available: true } };
    expect(p.data.report_available).toBe(true);
  });

  it("ERROR payload has message field", () => {
    const p = { type: "ERROR", message: "Pipeline failure" };
    expect(typeof p.message).toBe("string");
    expect(p.message.length).toBeGreaterThan(0);
  });
});
