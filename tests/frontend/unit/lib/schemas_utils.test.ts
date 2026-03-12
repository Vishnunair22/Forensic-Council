/**
 * Frontend Unit Tests — lib/schemas.ts & lib/utils.ts
 * =====================================================
 * Zod schema validation (boundary conditions, nested structures)
 * and Tailwind class utility function.
 *
 * Run: cd frontend && npm test -- tests/frontend/unit/lib/schemas_utils.test.ts
 */

import { AgentResultSchema, ReportSchema, HistorySchema } from "@/lib/schemas";
import { cn } from "@/lib/utils";

// ── Shared valid fixtures ─────────────────────────────────────────────────────

const validAgent = {
  id: "agent-1",
  name: "Image Analyst",
  role: "Image Integrity",
  result: "No manipulation detected.",
  confidence: 0.92,
};

const validReport = {
  id: "rpt-001",
  fileName: "CASE-1234567890",
  timestamp: "2025-01-01T00:00:00Z",
  summary: "Evidence appears authentic.",
  agents: [validAgent],
};

// ═══════════════════════════════════════════════════════════════════════════════
// AgentResultSchema
// ═══════════════════════════════════════════════════════════════════════════════

describe("AgentResultSchema", () => {
  describe("valid inputs", () => {
    it("accepts minimal valid agent", () => {
      expect(AgentResultSchema.safeParse(validAgent).success).toBe(true);
    });
    it("accepts optional thinking field", () => {
      expect(AgentResultSchema.safeParse({ ...validAgent, thinking: "Analyzing..." }).success).toBe(true);
    });
    it("accepts optional metadata field", () => {
      expect(AgentResultSchema.safeParse({ ...validAgent, metadata: { ela: 0.05 } }).success).toBe(true);
    });
    it("accepts confidence = 0 (boundary)", () => {
      expect(AgentResultSchema.safeParse({ ...validAgent, confidence: 0 }).success).toBe(true);
    });
    it("accepts confidence = 1 (boundary)", () => {
      expect(AgentResultSchema.safeParse({ ...validAgent, confidence: 1 }).success).toBe(true);
    });
    it("accepts negative confidence (schema allows any number)", () => {
      const r = AgentResultSchema.safeParse({ ...validAgent, confidence: -0.1 });
      // The schema uses z.number() with no range — should pass
      expect(r.success).toBe(true);
    });
    it("accepts confidence > 1 (schema allows any number)", () => {
      expect(AgentResultSchema.safeParse({ ...validAgent, confidence: 1.5 }).success).toBe(true);
    });
    it("preserves parsed data faithfully", () => {
      const r = AgentResultSchema.safeParse(validAgent);
      if (r.success) {
        expect(r.data.id).toBe("agent-1");
        expect(r.data.confidence).toBe(0.92);
      }
    });
  });

  describe("invalid inputs", () => {
    it("rejects missing id", () => {
      const { id: _, ...noId } = validAgent;
      expect(AgentResultSchema.safeParse(noId).success).toBe(false);
    });
    it("rejects missing name", () => {
      const { name: _, ...noName } = validAgent;
      expect(AgentResultSchema.safeParse(noName).success).toBe(false);
    });
    it("rejects missing role", () => {
      const { role: _, ...noRole } = validAgent;
      expect(AgentResultSchema.safeParse(noRole).success).toBe(false);
    });
    it("rejects missing result", () => {
      const { result: _, ...noResult } = validAgent;
      expect(AgentResultSchema.safeParse(noResult).success).toBe(false);
    });
    it("rejects missing confidence", () => {
      const { confidence: _, ...noConf } = validAgent;
      expect(AgentResultSchema.safeParse(noConf).success).toBe(false);
    });
    it("rejects non-numeric confidence", () => {
      expect(AgentResultSchema.safeParse({ ...validAgent, confidence: "high" }).success).toBe(false);
    });
    it("rejects null input", () => {
      expect(AgentResultSchema.safeParse(null).success).toBe(false);
    });
    it("rejects array input", () => {
      expect(AgentResultSchema.safeParse([validAgent]).success).toBe(false);
    });
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// ReportSchema
// ═══════════════════════════════════════════════════════════════════════════════

describe("ReportSchema", () => {
  describe("valid inputs", () => {
    it("accepts valid report with one agent", () => {
      expect(ReportSchema.safeParse(validReport).success).toBe(true);
    });
    it("accepts report with empty agents array", () => {
      expect(ReportSchema.safeParse({ ...validReport, agents: [] }).success).toBe(true);
    });
    it("accepts report with multiple agents", () => {
      const agents = [validAgent, { ...validAgent, id: "agent-2", name: "Audio Analyst" }];
      const r = ReportSchema.safeParse({ ...validReport, agents });
      expect(r.success).toBe(true);
      if (r.success) expect(r.data.agents).toHaveLength(2);
    });
    it("accepts agent with optional thinking in agents array", () => {
      const agents = [{ ...validAgent, thinking: "Deep analysis..." }];
      expect(ReportSchema.safeParse({ ...validReport, agents }).success).toBe(true);
    });
    it("preserves summary faithfully", () => {
      const r = ReportSchema.safeParse(validReport);
      if (r.success) expect(r.data.summary).toBe("Evidence appears authentic.");
    });
  });

  describe("invalid inputs", () => {
    it("rejects missing id", () => {
      const { id: _, ...noId } = validReport;
      expect(ReportSchema.safeParse(noId).success).toBe(false);
    });
    it("rejects missing fileName", () => {
      const { fileName: _, ...noFn } = validReport;
      expect(ReportSchema.safeParse(noFn).success).toBe(false);
    });
    it("rejects missing timestamp", () => {
      const { timestamp: _, ...noTs } = validReport;
      expect(ReportSchema.safeParse(noTs).success).toBe(false);
    });
    it("rejects missing summary", () => {
      const { summary: _, ...noSum } = validReport;
      expect(ReportSchema.safeParse(noSum).success).toBe(false);
    });
    it("rejects missing agents", () => {
      const { agents: _, ...noAgents } = validReport;
      expect(ReportSchema.safeParse(noAgents).success).toBe(false);
    });
    it("rejects agents as non-array", () => {
      expect(ReportSchema.safeParse({ ...validReport, agents: "not-array" }).success).toBe(false);
    });
    it("rejects invalid agent inside agents array", () => {
      expect(ReportSchema.safeParse({ ...validReport, agents: [{ bad: true }] }).success).toBe(false);
    });
    it("rejects numeric timestamp", () => {
      expect(ReportSchema.safeParse({ ...validReport, timestamp: 12345 }).success).toBe(false);
    });
    it("rejects null", () => {
      expect(ReportSchema.safeParse(null).success).toBe(false);
    });
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// HistorySchema
// ═══════════════════════════════════════════════════════════════════════════════

describe("HistorySchema", () => {
  it("accepts empty array", () => {
    expect(HistorySchema.safeParse([]).success).toBe(true);
  });
  it("accepts array of one report", () => {
    const r = HistorySchema.safeParse([validReport]);
    expect(r.success).toBe(true);
    if (r.success) expect(r.data).toHaveLength(1);
  });
  it("accepts array of many reports", () => {
    const reports = Array.from({ length: 5 }, (_, i) => ({ ...validReport, id: `r${i}` }));
    const r = HistorySchema.safeParse(reports);
    expect(r.success).toBe(true);
    if (r.success) expect(r.data).toHaveLength(5);
  });
  it("rejects non-array (object)", () => {
    expect(HistorySchema.safeParse(validReport).success).toBe(false);
  });
  it("rejects non-array (null)", () => {
    expect(HistorySchema.safeParse(null).success).toBe(false);
  });
  it("rejects non-array (string)", () => {
    expect(HistorySchema.safeParse("[]").success).toBe(false);
  });
  it("rejects array containing invalid report", () => {
    expect(HistorySchema.safeParse([{ id: "only-id" }]).success).toBe(false);
  });
  it("rejects mixed valid/invalid reports", () => {
    expect(HistorySchema.safeParse([validReport, { bad: true }]).success).toBe(false);
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// cn() utility
// ═══════════════════════════════════════════════════════════════════════════════

describe("cn() — Tailwind class merger", () => {
  it("returns empty string with no args", () => expect(cn()).toBe(""));
  it("merges two class strings", () => expect(cn("foo", "bar")).toBe("foo bar"));
  it("handles conditional false", () => expect(cn("base", false)).toBe("base"));
  it("handles conditional null", () => expect(cn("base", null as unknown as string)).toBe("base"));
  it("handles conditional undefined", () => expect(cn("base", undefined)).toBe("base"));
  it("handles truthy conditional", () => {
    const active = true;
    expect(cn("base", active && "active")).toBe("base active");
  });
  it("handles falsy conditional", () => {
    const active = false;
    expect(cn("base", active && "active")).toBe("base");
  });
  it("merges Tailwind conflict — later padding wins", () => {
    expect(cn("p-2", "p-4")).toBe("p-4");
  });
  it("merges Tailwind conflict — later text color wins", () => {
    expect(cn("text-red-500", "text-blue-500")).toBe("text-blue-500");
  });
  it("handles object syntax (clsx)", () => {
    expect(cn({ "text-red-500": true, "text-blue-500": false })).toBe("text-red-500");
  });
  it("handles array syntax (clsx)", () => {
    expect(cn(["bg-white", "rounded"])).toBe("bg-white rounded");
  });
  it("handles deeply nested clsx structures", () => {
    expect(cn(["a", ["b", "c"]])).toBe("a b c");
  });
  it("handles mixed clsx and twMerge", () => {
    const result = cn({ "p-2": true }, "p-8", ["text-sm"]);
    expect(result).toContain("p-8");
    expect(result).not.toContain("p-2");
    expect(result).toContain("text-sm");
  });
});
