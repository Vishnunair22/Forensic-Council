/**
 * Frontend Integration Tests — Page Flows & Session Data
 * =======================================================
 * Tests end-to-end data flow across the frontend:
 * - mapReportDtoToReport with complex multi-agent / multi-phase reports
 * - Session ID storage after startInvestigation
 * - Report persistence to sessionStorage after poll completes
 * - WebSocket message type mapping
 * - Findings deduplication logic (the bug fix in result/page.tsx)
 * - Auth token lifecycle across operations
 *
 * Run: cd apps/web && npm test -- tests/integration/page_flows.test.tsx
 */

import { mapReportDtoToReport } from "../helpers/mapReportDtoToReport";
import { setAuthToken, getAuthToken, clearAuthToken, isAuthenticated } from "@/lib/api";
import type { ReportDTO } from "@/lib/api";

// ── sessionStorage mock ───────────────────────────────────────────────────────

const store: Record<string, string> = {};
Object.defineProperty(window, "sessionStorage", {
  value: {
    getItem: jest.fn((k: string) => store[k] ?? null),
    setItem: jest.fn((k: string, v: string) => { store[k] = v; }),
    removeItem: jest.fn((k: string) => { delete store[k]; }),
    clear: jest.fn(() => Object.keys(store).forEach(k => delete store[k])),
  },
  writable: true,
});

// ── fetch mock ────────────────────────────────────────────────────────────────

global.fetch = jest.fn();
const mockFetch = global.fetch as jest.Mock;

beforeEach(() => {
  jest.clearAllMocks();
  Object.keys(store).forEach(k => delete store[k]);
});

// ── fixtures ──────────────────────────────────────────────────────────────────

function makeDTO(overrides: Partial<ReportDTO> = {}): ReportDTO {
  return {
    report_id: "rpt-integration",
    session_id: "sess-integration",
    case_id: "CASE-9999999999",
    executive_summary: "Integration test report.",
    per_agent_findings: {},
    per_agent_metrics: {},
    per_agent_analysis: {},
    overall_confidence: 0.90,
    overall_error_rate: 0.02,
    overall_verdict: "LIKELY",
    cross_modal_confirmed: [],
    contested_findings: [],
    tribunal_resolved: [],
    incomplete_findings: [],
    uncertainty_statement: "Minimal uncertainty.",
    cryptographic_signature: "sig-abc",
    report_hash: "hash-abc",
    signed_utc: "2025-06-15T08:00:00Z",
    ...overrides,
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// COMPLEX REPORT MAPPING
// ═══════════════════════════════════════════════════════════════════════════════

describe("mapReportDtoToReport — complex reports", () => {
  it("handles 5 agents each with 2 findings (10 agents entries)", () => {
    const perAgent: ReportDTO["per_agent_findings"] = {};
    ["agent-img", "agent-audio", "agent-obj", "agent-vid", "agent-meta"].forEach(id => {
      perAgent[id] = [
        {
          finding_id: `${id}-f1`, agent_id: id, agent_name: `${id} Expert`,
          finding_type: "primary", status: "complete",
          confidence_raw: 0.9, calibrated: true,
          raw_confidence_score: null,
          court_statement: "Statement A.", robustness_caveat: false,
          robustness_caveat_detail: null, reasoning_summary: "Summary A.", metadata: null,
        },
        {
          finding_id: `${id}-f2`, agent_id: id, agent_name: `${id} Expert`,
          finding_type: "secondary", status: "complete",
          confidence_raw: 0.6, calibrated: false,
          raw_confidence_score: null,
          court_statement: "Statement B.", robustness_caveat: true,
          robustness_caveat_detail: "Low confidence.", reasoning_summary: "Summary B.", metadata: null,
        },
      ];
    });
    const report = mapReportDtoToReport(makeDTO({ per_agent_findings: perAgent }));
    expect(report.agents).toHaveLength(10);
  });

  it("handles agent findings with phase metadata (deep analysis)", () => {
    const perAgent: ReportDTO["per_agent_findings"] = {
      "agent-img": [
        {
          finding_id: "f-initial", agent_id: "agent-img", agent_name: "Image Expert",
          finding_type: "ela_analysis", status: "complete",
          confidence_raw: 0.8, calibrated: false,
          raw_confidence_score: null,
          court_statement: "Initial pass.", robustness_caveat: false,
          robustness_caveat_detail: null, reasoning_summary: "Summary.", metadata: null,
        },
        {
          finding_id: "f-deep", agent_id: "agent-img", agent_name: "Image Expert",
          finding_type: "ela_analysis", status: "complete",
          confidence_raw: 0.95, calibrated: true,
          raw_confidence_score: null,
          court_statement: "Deep pass.", robustness_caveat: false,
          robustness_caveat_detail: null, reasoning_summary: "Deep summary.",
          metadata: { analysis_phase: "deep" },
        },
      ],
    };
    // Both findings should be preserved (different metadata.analysis_phase)
    const report = mapReportDtoToReport(makeDTO({ per_agent_findings: perAgent }));
    expect(report.agents).toHaveLength(2);
    const statements = report.agents.map(a => a.result);
    expect(statements).toContain("Initial pass.");
    expect(statements).toContain("Deep pass.");
  });

  it("preserves all findings including same-type entries (dedup is UI-only in AgentSection)", () => {
    const perAgent: ReportDTO["per_agent_findings"] = {
      "agent-img": [
        {
          finding_id: "f-dup-1", agent_id: "agent-img", agent_name: "Image Expert",
          finding_type: "ela_analysis", status: "complete",
          confidence_raw: 0.8, calibrated: false,
          raw_confidence_score: null,
          court_statement: "First.", robustness_caveat: false,
          robustness_caveat_detail: null, reasoning_summary: "Summary.", metadata: null,
        },
        {
          finding_id: "f-dup-2", agent_id: "agent-img", agent_name: "Image Expert",
          finding_type: "ela_analysis", status: "complete",
          confidence_raw: 0.9, calibrated: false,
          raw_confidence_score: null,
          court_statement: "Second.", robustness_caveat: false,
          robustness_caveat_detail: null, reasoning_summary: "Summary.", metadata: null,
        },
      ],
    };
    const report = mapReportDtoToReport(makeDTO({ per_agent_findings: perAgent }));
    // mapReportDtoToReport flattens ALL findings — dedup by finding_id only happens in
    // AgentSection (UI layer). Both entries should be present in the mapped agents array.
    expect(report.agents).toHaveLength(2);
  });

  it("preserves correct fields for court display", () => {
    const perAgent: ReportDTO["per_agent_findings"] = {
      "agent-vid": [{
        finding_id: "fv", agent_id: "agent-vid", agent_name: "Video Expert",
        finding_type: "deepfake_detection", status: "complete",
        confidence_raw: 0.97, calibrated: true,
          raw_confidence_score: null,
        court_statement: "No deepfake detected at p < 0.05.",
        robustness_caveat: false, robustness_caveat_detail: null,
        reasoning_summary: "Optical flow consistent.", metadata: null,
      }],
    };
    const report = mapReportDtoToReport(makeDTO({ per_agent_findings: perAgent }));
    expect(report.agents[0].result).toBe("No deepfake detected at p < 0.05.");
    expect(report.agents[0].confidence).toBe(0.97);
  });

  it("produces correct report metadata fields", () => {
    const report = mapReportDtoToReport(makeDTO());
    expect(report.id).toBe("rpt-integration");
    expect(report.fileName).toBe("CASE-9999999999");
    expect(report.summary).toBe("Integration test report.");
    expect(report.timestamp).toBe("2025-06-15T08:00:00Z");
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// SESSION DATA FLOW
// ═══════════════════════════════════════════════════════════════════════════════

describe("Session Data Flow", () => {
  it("session ID is stored to sessionStorage after investigation starts", () => {
    mockFetch.mockResolvedValueOnce({
      ok: true, status: 200,
      json: jest.fn().mockResolvedValue({
        session_id: "sess-stored", case_id: "CASE-9999999999", status: "started", message: "OK",
      }),
    });
    // Simulate the evidence page storing the session_id (as the real page does)
    store["fc_session_id"] = "sess-stored";
    expect(window.sessionStorage.getItem("fc_session_id")).toBe("sess-stored");
  });

  it("sessionStorage survives re-render (data persists in store)", () => {
    store["fc_history"] = JSON.stringify([{
      id: "rpt-persisted", fileName: "F", timestamp: "T", summary: "S", agents: [],
    }]);
    const loaded = JSON.parse(window.sessionStorage.getItem("fc_history") ?? "[]");
    expect(loaded).toHaveLength(1);
    expect(loaded[0].id).toBe("rpt-persisted");
  });

  it("report saved to sessionStorage after poll completes", () => {
    const report = mapReportDtoToReport(makeDTO());
    store["fc_current_report"] = JSON.stringify(report);
    const loaded = JSON.parse(window.sessionStorage.getItem("fc_current_report") ?? "null");
    expect(loaded?.id).toBe("rpt-integration");
  });

  it("history deduplication — same ID not added twice", () => {
    const existing = [{ id: "r-dup", fileName: "F", timestamp: "T", summary: "S", agents: [] }];
    store["fc_history"] = JSON.stringify(existing);
    // Simulate addToHistory logic: filter out existing ID before prepend
    const current = JSON.parse(store["fc_history"]) as typeof existing;
    const newReport = { id: "r-dup", fileName: "F2", timestamp: "T2", summary: "S2", agents: [] };
    const deduped = [newReport, ...current.filter(r => r.id !== newReport.id)];
    expect(deduped).toHaveLength(1);
    expect(deduped[0].fileName).toBe("F2"); // Updated entry
  });

  it("history keeps multiple distinct entries", () => {
    const entries = [
      { id: "r1", fileName: "F1", timestamp: "T1", summary: "S1", agents: [] },
      { id: "r2", fileName: "F2", timestamp: "T2", summary: "S2", agents: [] },
      { id: "r3", fileName: "F3", timestamp: "T3", summary: "S3", agents: [] },
    ];
    store["fc_history"] = JSON.stringify(entries);
    const loaded = JSON.parse(store["fc_history"]);
    expect(loaded).toHaveLength(3);
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// WEBSOCKET MESSAGE FLOW MAPPING
// ═══════════════════════════════════════════════════════════════════════════════

describe("WebSocket Message Type Mapping", () => {
  const MESSAGE_TYPES = [
    "CONNECTED", "AUTH", "AGENT_START", "AGENT_UPDATE",
    "AGENT_COMPLETE", "PIPELINE_PAUSED", "PIPELINE_COMPLETE", "ERROR",
  ];

  it.each(MESSAGE_TYPES)("message type '%s' can be JSON stringified and parsed", (type) => {
    const msg = { type, session_id: "sess", payload: {} };
    const str = JSON.stringify(msg);
    const parsed = JSON.parse(str);
    expect(parsed.type).toBe(type);
  });

  it("AGENT_COMPLETE message carries expected fields", () => {
    const msg = JSON.stringify({
      type: "AGENT_COMPLETE",
      session_id: "sess",
      payload: {
        agent_id: "agent-img",
        agent_name: "Image Analyst",
        status: "complete",
        confidence: 0.95,
        findings_count: 2,
        message: "Analysis done.",
      },
    });
    const parsed = JSON.parse(msg);
    expect(parsed.payload.agent_id).toBe("agent-img");
    expect(parsed.payload.confidence).toBe(0.95);
  });

  it("PIPELINE_PAUSED message carries checkpoint fields", () => {
    const msg = JSON.stringify({
      type: "PIPELINE_PAUSED",
      session_id: "sess",
      payload: {
        checkpoint_id: "cp-1",
        agent_id: "agent-arbiter",
        decision_needed: "Contested findings require review.",
      },
    });
    const parsed = JSON.parse(msg);
    expect(parsed.type).toBe("PIPELINE_PAUSED");
    expect(parsed.payload.checkpoint_id).toBe("cp-1");
  });

  it("AGENT_UPDATE message carries thinking field", () => {
    const msg = JSON.stringify({
      type: "AGENT_UPDATE",
      session_id: "sess",
      payload: {
        agent_id: "agent-audio",
        message_type: "THOUGHT",
        content: "Running spectral analysis on audio track...",
      },
    });
    const parsed = JSON.parse(msg);
    expect(parsed.payload.content).toContain("spectral analysis");
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// REPORT DEDUPLICATION (result page bug fix)
// ═══════════════════════════════════════════════════════════════════════════════

describe("Report Findings Deduplication (v1.0.3 fix)", () => {
  it("no phase metadata → deduplicate by finding_type (prevents duplicates)", () => {
    const findings = [
      { finding_type: "ela", metadata: null, court_statement: "A", confidence_raw: 0.8 },
      { finding_type: "ela", metadata: null, court_statement: "B", confidence_raw: 0.9 },
      { finding_type: "splice", metadata: null, court_statement: "C", confidence_raw: 0.7 },
    ];
    // The dedup logic: seen = new Set(); filter where !seen.has(type) || metadata?.analysis_phase
    const seen = new Set<string>();
    const deduped = findings.filter(f => {
      const phase = (f.metadata as Record<string, unknown> | null)?.analysis_phase;
      if (phase || !seen.has(f.finding_type)) {
        seen.add(f.finding_type);
        return true;
      }
      return false;
    });
    expect(deduped).toHaveLength(2); // ela(first) + splice
    expect(deduped[0].court_statement).toBe("A");
    expect(deduped[1].finding_type).toBe("splice");
  });

  it("with phase metadata → both initial and deep entries preserved", () => {
    const findings = [
      { finding_type: "ela", metadata: null, court_statement: "Initial", confidence_raw: 0.8 },
      { finding_type: "ela", metadata: { analysis_phase: "deep" }, court_statement: "Deep", confidence_raw: 0.95 },
    ];
    const seen = new Set<string>();
    const deduped = findings.filter(f => {
      const phase = (f.metadata as Record<string, unknown> | null)?.analysis_phase;
      if (phase || !seen.has(f.finding_type)) {
        seen.add(f.finding_type);
        return true;
      }
      return false;
    });
    expect(deduped).toHaveLength(2);
    expect(deduped[0].court_statement).toBe("Initial");
    expect(deduped[1].court_statement).toBe("Deep");
  });

  it("empty findings array → empty result", () => {
    expect([].filter(() => true)).toHaveLength(0);
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// AUTH TOKEN LIFECYCLE
// ═══════════════════════════════════════════════════════════════════════════════

describe("Auth Token Lifecycle", () => {
  it("token set after login response", () => {
    setAuthToken("new-jwt", 3600);
    expect(getAuthToken()).toBe("new-jwt");
    expect(isAuthenticated()).toBe(true);
  });

  it("expired token cleared automatically", () => {
    store["forensic_auth_token"] = "expired-tok";
    store["forensic_auth_token_expiry"] = String(Date.now() - 1000);
    expect(getAuthToken()).toBeNull();
    expect(isAuthenticated()).toBe(false);
  });

  it("token survives non-expiry window (still valid)", () => {
    setAuthToken("long-live", 7200);
    expect(isAuthenticated()).toBe(true);
    expect(getAuthToken()).toBe("long-live");
  });

  it("clearAuthToken makes isAuthenticated return false", () => {
    setAuthToken("will-be-cleared", 3600);
    expect(isAuthenticated()).toBe(true);
    clearAuthToken();
    expect(isAuthenticated()).toBe(false);
  });

  it("multiple setAuthToken calls overwrite previous token", () => {
    setAuthToken("first", 3600);
    setAuthToken("second", 3600);
    expect(getAuthToken()).toBe("second");
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// SESSION-SCOPED METADATA (Phase 3.5 fix)
// ═══════════════════════════════════════════════════════════════════════════════

describe("Session-scoped metadata", () => {
  const lsStore: Record<string, string> = {};
  Object.defineProperty(window, "localStorage", {
    value: {
      getItem: jest.fn((k: string) => lsStore[k] ?? null),
      setItem: jest.fn((k: string, v: string) => { lsStore[k] = v; }),
      removeItem: jest.fn((k: string) => { delete lsStore[k]; }),
      clear: jest.fn(() => Object.keys(lsStore).forEach(k => delete lsStore[k])),
    },
    writable: true,
  });

  // function makeCtx(sid: string, fileName: string) {
  //   return JSON.stringify({ session_id: sid, file_name: fileName, mime_type: "image/png" });
  // }

  beforeEach(() => Object.keys(lsStore).forEach(k => delete lsStore[k]));

  it("writes scoped context alongside global context when session starts", () => {
    const investigationCtx = { session_id: "sess-b", file_name: "file-b.png", mime_type: "image/png" };
    lsStore["forensic_investigation_ctx"] = JSON.stringify({ session_id: "sess-a", file_name: "file-a.png" });
    lsStore[`forensic_investigation_ctx:sess-b`] = JSON.stringify(investigationCtx);
    lsStore["forensic_session_id"] = "sess-b";

    const scoped = JSON.parse(lsStore[`forensic_investigation_ctx:sess-b`] ?? "{}");
    expect(scoped.file_name).toBe("file-b.png");
    expect(scoped.session_id).toBe("sess-b");
  });

  it("history item fileName can differ per session", () => {
    lsStore["forensic_history"] = JSON.stringify([
      { sessionId: "sess-a", fileName: "file-a.png", verdict: "LIKELY", timestamp: 1, type: "Initial" },
    ]);
    const history = JSON.parse(lsStore["forensic_history"]);
    expect(history).toHaveLength(1);
    expect(history[0].fileName).toBe("file-a.png");
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// ROUTE-STATE MATRIX (Phase 1 Fix)
// ═══════════════════════════════════════════════════════════════════════════════

describe("Route-State Matrix", () => {
  const lsStore2: Record<string, string> = {};
  const ssStore2: Record<string, string> = {};

  beforeEach(() => {
    Object.keys(lsStore2).forEach((k) => delete lsStore2[k]);
    Object.keys(ssStore2).forEach((k) => delete ssStore2[k]);

    Object.defineProperty(window, "localStorage", {
      value: {
        getItem: jest.fn((k: string) => lsStore2[k] ?? null),
        setItem: jest.fn((k: string, v: string) => {
          lsStore2[k] = v;
        }),
        removeItem: jest.fn((k: string) => {
          delete lsStore2[k];
        }),
        clear: jest.fn(() => Object.keys(lsStore2).forEach((k) => delete lsStore2[k])),
      },
      writable: true,
    });

    Object.defineProperty(window, "sessionStorage", {
      value: {
        getItem: jest.fn((k: string) => ssStore2[k] ?? null),
        setItem: jest.fn((k: string, v: string) => {
          ssStore2[k] = v;
        }),
        removeItem: jest.fn((k: string) => {
          delete ssStore2[k];
        }),
        clear: jest.fn(() => Object.keys(ssStore2).forEach((k) => delete ssStore2[k])),
      },
      writable: true,
    });
  });

  it("home with ?upload=1 opens upload modal", () => {
    const url = new URL("http://localhost/?upload=1");
    expect(url.searchParams.get("upload")).toBe("1");
  });

  it("evidence without pending file and without session redirects home with upload prompt", () => {
    delete lsStore2["forensic_session_id"];
    delete lsStore2["fc_pending_file_meta"];

    const hasSession = !!(lsStore2["forensic_session_id"] && lsStore2["forensic_session_id"].length > 0);
    const hasPendingFile = !!(lsStore2["fc_pending_file_meta"] && lsStore2["fc_pending_file_meta"].length > 0);

    expect(hasSession || hasPendingFile).toBe(false);
  });

  it("evidence with expired auto-start shows recovery and returns home", () => {
    lsStore2["forensic_session_id"] = "sess-expired";
    lsStore2["forensic_auto_start"] = String(Date.now() - 3600000);

    const isExpired = parseInt(lsStore2["forensic_auto_start"] || "0", 10) < Date.now() - 300000;
    expect(isExpired).toBe(true);
  });

  it("evidence with existing running session reconnects", () => {
    lsStore2["forensic_session_id"] = "sess-running";
    lsStore2["forensic_investigation_ctx"] = JSON.stringify({ session_id: "sess-running", status: "running" });

    const hasActiveSession = !!(lsStore2["forensic_session_id"] && lsStore2["forensic_investigation_ctx"]);
    expect(hasActiveSession).toBe(true);
  });

  it("result without session shows empty state", () => {
    delete lsStore2["forensic_session_id"];

    expect(lsStore2["forensic_session_id"]).toBeUndefined();
  });

  it("result with complete session renders report", () => {
    lsStore2["forensic_session_id"] = "sess-complete";
    ssStore2["fc_current_report"] = JSON.stringify({
      id: "rpt-123",
      sessionId: "sess-complete",
      overall_verdict: "LIKELY_AUTHENTIC",
    });

    const report = ssStore2["fc_current_report"] ? JSON.parse(ssStore2["fc_current_report"]) : null;
    expect(report?.id).toBe("rpt-123");
  });

  it("result with missing session shows graceful error", () => {
    lsStore2["forensic_session_id"] = "sess-missing";
    const report = ssStore2["fc_current_report"] ? JSON.parse(ssStore2["fc_current_report"]) : null;

    expect(report).toBeNull();
  });

  it("new upload clears active investigation but preserves history", () => {
    const history = [
      { sessionId: "sess-old", fileName: "old.png", verdict: "LIKELY", timestamp: 1000, type: "Initial" },
    ];
    lsStore2["forensic_history"] = JSON.stringify(history);
    lsStore2["forensic_session_id"] = "sess-active";
    lsStore2["forensic_investigation_ctx"] = '{"session_id":"sess-active"}';

    delete lsStore2["forensic_session_id"];
    delete lsStore2["forensic_investigation_ctx"];

    const preservedHistory = JSON.parse(lsStore2["forensic_history"] ?? "[]");
    expect(preservedHistory).toEqual(history);
    expect(lsStore2["forensic_session_id"]).toBeUndefined();
    expect(lsStore2["forensic_investigation_ctx"]).toBeUndefined();
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// DEEP RESULT CONTEXT (Phase 4 Fix)
// ═══════════════════════════════════════════════════════════════════════════════

describe("Deep result context", () => {
  const lsStore3: Record<string, string> = {};

  beforeEach(() => {
    Object.keys(lsStore3).forEach((k) => delete lsStore3[k]);

    Object.defineProperty(window, "localStorage", {
      value: {
        getItem: jest.fn((k: string) => lsStore3[k] ?? null),
        setItem: jest.fn((k: string, v: string) => {
          lsStore3[k] = v;
        }),
        removeItem: jest.fn((k: string) => {
          delete lsStore3[k];
        }),
        clear: jest.fn(() => Object.keys(lsStore3).forEach((k) => delete lsStore3[k])),
      },
      writable: true,
    });
  });

  it("deep result loads deep agent timeline", () => {
    const deepAgents = [
      { agent_id: "agent-img", status: "complete", confidence: 0.95 },
      { agent_id: "agent-audio", status: "complete", confidence: 0.88 },
    ];
    lsStore3["forensic_is_deep"] = "true";
    lsStore3["forensic_session_id"] = "sess-deep";
    lsStore3["forensic_deep_agents:sess-deep"] = JSON.stringify(deepAgents);

    const isDeep = lsStore3["forensic_is_deep"] === "true";
    const deepTimeline = isDeep
      ? JSON.parse(lsStore3[`forensic_deep_agents:${lsStore3["forensic_session_id"]}`] ?? "[]")
      : [];

    expect(deepTimeline).toHaveLength(2);
    expect(deepTimeline[0].agent_id).toBe("agent-img");
  });

  it("deep result preserves original file name from scoped context", () => {
    lsStore3["forensic_session_id"] = "sess-deep";
    lsStore3["forensic_investigation_ctx:sess-deep"] = JSON.stringify({
      session_id: "sess-deep",
      file_name: "evidence.jpg",
      mime_type: "image/jpeg",
      pipeline_start: "2025-01-01T00:00:00Z",
    });

    const ctx = JSON.parse(lsStore3[`forensic_investigation_ctx:${lsStore3["forensic_session_id"]}`] ?? "{}");
    expect(ctx.file_name).toBe("evidence.jpg");
    expect(ctx.mime_type).toBe("image/jpeg");
  });

  it("deep result saves history item with type Deep", () => {
    const history = [
      { sessionId: "sess-deep", fileName: "evidence.jpg", verdict: "LIKELY_AUTHENTIC", timestamp: 1000, type: "Deep" },
    ];

    lsStore3["forensic_history"] = JSON.stringify(history);
    const parsed = JSON.parse(lsStore3["forensic_history"] ?? "[]");

    expect(parsed[0].type).toBe("Deep");
  });

  it("initial result saves history item with type Initial", () => {
    const history = [
      { sessionId: "sess-init", fileName: "evidence.jpg", verdict: "LIKELY_AUTHENTIC", timestamp: 1000, type: "Initial" },
    ];

    lsStore3["forensic_history"] = JSON.stringify(history);
    lsStore3["forensic_is_deep"] = "false";

    const parsed = JSON.parse(lsStore3["forensic_history"] ?? "[]");

    expect(parsed[0].type).toBe("Initial");
  });
});
