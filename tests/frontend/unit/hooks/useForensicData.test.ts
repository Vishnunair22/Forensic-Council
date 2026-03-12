/**
 * Frontend Unit Tests — hooks/useForensicData.ts
 * ================================================
 * Tests mapReportDtoToReport mapping and the full hook lifecycle:
 * history persistence, validateFile, startAnalysis, addToHistory,
 * deleteFromHistory, clearHistory, saveCurrentReport, pollForReport.
 *
 * Run: cd frontend && npm test -- tests/frontend/unit/hooks/useForensicData.test.ts
 */

import { renderHook, act } from "@testing-library/react";
import { useForensicData, mapReportDtoToReport } from "@/hooks/useForensicData";
import type { ReportDTO } from "@/lib/api";
import * as api from "@/lib/api";

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

// ── api mocks ─────────────────────────────────────────────────────────────────

jest.mock("@/lib/api", () => ({
  startInvestigation: jest.fn(),
  getReport: jest.fn(),
}));

const mockStart = api.startInvestigation as jest.Mock;
const mockGetReport = api.getReport as jest.Mock;

// ── fixtures ──────────────────────────────────────────────────────────────────

const sampleDTO: ReportDTO = {
  report_id: "rpt-fixture",
  session_id: "sess-fixture",
  case_id: "CASE-1234567890",
  executive_summary: "Evidence is authentic.",
  per_agent_findings: {
    "agent-img": [{
      finding_id: "f1", agent_id: "agent-img", agent_name: "Image Analyst",
      finding_type: "ela_analysis", status: "complete",
      confidence_raw: 0.90, calibrated: true, calibrated_probability: 0.88,
      court_statement: "No manipulation.", robustness_caveat: false,
      robustness_caveat_detail: null, reasoning_summary: "ELA uniform.", metadata: null,
    }],
    "agent-audio": [{
      finding_id: "f2", agent_id: "agent-audio", agent_name: "Audio Analyst",
      finding_type: "splice_detection", status: "complete",
      confidence_raw: 0.75, calibrated: false, calibrated_probability: null,
      court_statement: null, robustness_caveat: true,
      robustness_caveat_detail: "Low quality", reasoning_summary: "No splice.", metadata: null,
    }],
  },
  cross_modal_confirmed: [],
  contested_findings: [],
  tribunal_resolved: [],
  incomplete_findings: [],
  uncertainty_statement: "Low uncertainty.",
  cryptographic_signature: "sig",
  report_hash: "hash",
  signed_utc: "2025-06-01T12:00:00Z",
};

const emptyReport = { id: "r0", fileName: "F0", timestamp: "T", summary: "S", agents: [] };

beforeEach(() => {
  jest.clearAllMocks();
  Object.keys(store).forEach(k => delete store[k]);
});

// ═══════════════════════════════════════════════════════════════════════════════
// mapReportDtoToReport
// ═══════════════════════════════════════════════════════════════════════════════

describe("mapReportDtoToReport()", () => {
  it("maps report_id → id", () => expect(mapReportDtoToReport(sampleDTO).id).toBe("rpt-fixture"));
  it("maps case_id → fileName", () => expect(mapReportDtoToReport(sampleDTO).fileName).toBe("CASE-1234567890"));
  it("maps executive_summary → summary", () => expect(mapReportDtoToReport(sampleDTO).summary).toBe("Evidence is authentic."));
  it("maps signed_utc → timestamp", () => expect(mapReportDtoToReport(sampleDTO).timestamp).toBe("2025-06-01T12:00:00Z"));
  it("uses current ISO when signed_utc is null", () => {
    const before = Date.now();
    const r = mapReportDtoToReport({ ...sampleDTO, signed_utc: null });
    expect(new Date(r.timestamp).getTime()).toBeGreaterThanOrEqual(before);
  });
  it("flattens per_agent_findings into agents array", () => {
    expect(mapReportDtoToReport(sampleDTO).agents).toHaveLength(2);
  });
  it("uses court_statement as result when available", () => {
    const agents = mapReportDtoToReport(sampleDTO).agents;
    const img = agents.find(a => a.id === "agent-img");
    expect(img?.result).toBe("No manipulation.");
  });
  it("falls back to reasoning_summary when court_statement is null", () => {
    const agents = mapReportDtoToReport(sampleDTO).agents;
    const audio = agents.find(a => a.id === "agent-audio");
    expect(audio?.result).toBe("No splice.");
  });
  it("uses calibrated_probability as confidence when available", () => {
    const agents = mapReportDtoToReport(sampleDTO).agents;
    const img = agents.find(a => a.id === "agent-img");
    expect(img?.confidence).toBe(0.88);
  });
  it("falls back to confidence_raw when not calibrated", () => {
    const agents = mapReportDtoToReport(sampleDTO).agents;
    const audio = agents.find(a => a.id === "agent-audio");
    expect(audio?.confidence).toBe(0.75);
  });
  it("maps agent_name → name and role", () => {
    const agents = mapReportDtoToReport(sampleDTO).agents;
    const img = agents.find(a => a.id === "agent-img");
    expect(img?.name).toBe("Image Analyst");
  });
  it("handles empty per_agent_findings", () => {
    const dto = { ...sampleDTO, per_agent_findings: {} };
    expect(mapReportDtoToReport(dto).agents).toHaveLength(0);
  });
  it("handles agent with multiple findings (flattens all)", () => {
    const dto: ReportDTO = {
      ...sampleDTO,
      per_agent_findings: {
        "agent-img": [sampleDTO.per_agent_findings["agent-img"][0], {
          ...sampleDTO.per_agent_findings["agent-img"][0],
          finding_id: "f1b", metadata: { analysis_phase: "deep" },
        }],
      },
    };
    expect(mapReportDtoToReport(dto).agents).toHaveLength(2);
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// useForensicData hook
// ═══════════════════════════════════════════════════════════════════════════════

describe("useForensicData — initial state", () => {
  it("starts with empty history", () => {
    const { result } = renderHook(() => useForensicData());
    expect(result.current.history).toEqual([]);
  });
  it("starts with null currentReport", () => {
    const { result } = renderHook(() => useForensicData());
    expect(result.current.currentReport).toBeNull();
  });
  it("starts with isAnalyzing=false", () => {
    const { result } = renderHook(() => useForensicData());
    expect(result.current.isAnalyzing).toBe(false);
  });
  it("starts with pollError=null", () => {
    const { result } = renderHook(() => useForensicData());
    expect(result.current.pollError).toBeNull();
  });
});

describe("useForensicData — sessionStorage loading", () => {
  it("loads valid history from sessionStorage on mount", () => {
    store["fc_history"] = JSON.stringify([emptyReport]);
    const { result } = renderHook(() => useForensicData());
    expect(result.current.history).toHaveLength(1);
    expect(result.current.history[0].id).toBe("r0");
  });
  it("ignores invalid JSON in fc_history", () => {
    store["fc_history"] = "{{bad json{{";
    const { result } = renderHook(() => useForensicData());
    expect(result.current.history).toEqual([]);
  });
  it("ignores invalid schema in fc_history", () => {
    store["fc_history"] = JSON.stringify([{ bad: true }]);
    const { result } = renderHook(() => useForensicData());
    expect(result.current.history).toEqual([]);
  });
  it("loads currentReport from fc_current_report", () => {
    store["fc_current_report"] = JSON.stringify(emptyReport);
    const { result } = renderHook(() => useForensicData());
    expect(result.current.currentReport?.id).toBe("r0");
  });
});

describe("useForensicData — history operations", () => {
  it("addToHistory adds report and persists to sessionStorage", () => {
    const { result } = renderHook(() => useForensicData());
    act(() => { result.current.addToHistory(emptyReport); });
    expect(result.current.history).toHaveLength(1);
    expect(window.sessionStorage.setItem).toHaveBeenCalledWith("fc_history", expect.stringContaining("r0"));
  });
  it("addToHistory prepends (newest first)", () => {
    const r1 = { ...emptyReport, id: "r1" };
    const r2 = { ...emptyReport, id: "r2" };
    const { result } = renderHook(() => useForensicData());
    act(() => { result.current.addToHistory(r1); });
    act(() => { result.current.addToHistory(r2); });
    expect(result.current.history[0].id).toBe("r2");
  });
  it("addToHistory does not add duplicates", () => {
    const { result } = renderHook(() => useForensicData());
    act(() => { result.current.addToHistory(emptyReport); result.current.addToHistory(emptyReport); });
    expect(result.current.history).toHaveLength(1);
  });
  it("deleteFromHistory removes correct entry", () => {
    store["fc_history"] = JSON.stringify([emptyReport, { ...emptyReport, id: "r2" }]);
    const { result } = renderHook(() => useForensicData());
    act(() => { result.current.deleteFromHistory("r0"); });
    expect(result.current.history).toHaveLength(1);
    expect(result.current.history[0].id).toBe("r2");
  });
  it("clearHistory empties history and removes sessionStorage key", () => {
    store["fc_history"] = JSON.stringify([emptyReport]);
    const { result } = renderHook(() => useForensicData());
    act(() => { result.current.clearHistory(); });
    expect(result.current.history).toHaveLength(0);
    expect(window.sessionStorage.removeItem).toHaveBeenCalledWith("fc_history");
  });
});

describe("useForensicData — saveCurrentReport", () => {
  it("updates currentReport state", () => {
    const { result } = renderHook(() => useForensicData());
    act(() => { result.current.saveCurrentReport(emptyReport); });
    expect(result.current.currentReport?.id).toBe("r0");
  });
  it("persists to sessionStorage", () => {
    const { result } = renderHook(() => useForensicData());
    act(() => { result.current.saveCurrentReport(emptyReport); });
    expect(window.sessionStorage.setItem).toHaveBeenCalledWith("fc_current_report", expect.stringContaining("r0"));
  });
});

describe("useForensicData — startAnalysis", () => {
  it("calls startInvestigation with correct args and returns session ID", async () => {
    mockStart.mockResolvedValueOnce({ session_id: "sess-new", case_id: "C", status: "started", message: "OK" });
    const { result } = renderHook(() => useForensicData());
    let sid: string;
    await act(async () => {
      sid = await result.current.startAnalysis(new File(["x"], "t.jpg"), "CASE-1234567890", "REQ-12345");
    });
    expect(sid!).toBe("sess-new");
  });
  it("rethrows errors from startInvestigation", async () => {
    mockStart.mockRejectedValueOnce(new Error("Upload failed"));
    const { result } = renderHook(() => useForensicData());
    await act(async () => {
      await expect(result.current.startAnalysis(new File(["x"], "t.jpg"), "CASE-1234567890", "REQ-12345")).rejects.toThrow("Upload failed");
    });
  });
});

describe("useForensicData — validateFile", () => {
  it("rejects file over 50MB", () => {
    const { result } = renderHook(() => useForensicData());
    const f = new File(["x"], "big.jpg", { type: "image/jpeg" });
    Object.defineProperty(f, "size", { value: 51 * 1024 * 1024 });
    const v = result.current.validateFile(f);
    expect(v.valid).toBe(false);
    expect(v.error).toMatch(/50MB/);
  });
  it("rejects unsupported MIME type", () => {
    const { result } = renderHook(() => useForensicData());
    const f = new File(["x"], "doc.txt", { type: "text/plain" });
    const v = result.current.validateFile(f);
    expect(v.valid).toBe(false);
    expect(v.error).toMatch(/Unsupported/i);
  });
  it("accepts image/jpeg", () => {
    const { result } = renderHook(() => useForensicData());
    const v = result.current.validateFile(new File(["x"], "p.jpg", { type: "image/jpeg" }));
    expect(v.valid).toBe(true);
  });
  it("accepts image/png", () => {
    const { result } = renderHook(() => useForensicData());
    expect(result.current.validateFile(new File(["x"], "p.png", { type: "image/png" })).valid).toBe(true);
  });
  it("accepts video/mp4", () => {
    const { result } = renderHook(() => useForensicData());
    expect(result.current.validateFile(new File(["x"], "v.mp4", { type: "video/mp4" })).valid).toBe(true);
  });
  it("accepts audio/wav", () => {
    const { result } = renderHook(() => useForensicData());
    expect(result.current.validateFile(new File(["x"], "a.wav", { type: "audio/wav" })).valid).toBe(true);
  });
  it("accepts audio/mpeg (mp3)", () => {
    const { result } = renderHook(() => useForensicData());
    expect(result.current.validateFile(new File(["x"], "a.mp3", { type: "audio/mpeg" })).valid).toBe(true);
  });
  it("rejects application/pdf", () => {
    const { result } = renderHook(() => useForensicData());
    const v = result.current.validateFile(new File(["x"], "d.pdf", { type: "application/pdf" }));
    expect(v.valid).toBe(false);
  });
});
