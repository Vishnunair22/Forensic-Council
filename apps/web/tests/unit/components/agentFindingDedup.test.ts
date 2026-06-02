/**
 * Unit Tests — Agent finding dedup / staleness guard
 * ===================================================
 * Locks the contract that the agent-findings card displays exactly the backend
 * findings with no stale entries:
 *   - one finding per tool (no duplicate tool rows)
 *   - a deep-phase finding always supersedes a stale initial-phase one
 *   - distinct backend findings are preserved verbatim (none silently dropped)
 *
 * Run: cd apps/web && npm test -- tests/unit/components/agentFindingDedup.test.ts
 */
import { dedupeAndFilter } from "@/components/ui/AgentFindingCard";
import type { AgentFindingDTO } from "@/lib/api";

function finding(
  tool: string,
  verdict: string,
  phase: "initial" | "deep",
  summary: string,
): AgentFindingDTO {
  return {
    finding_id: `${tool}-${phase}`,
    finding_type: tool,
    evidence_verdict: verdict,
    reasoning_summary: summary,
    severity_tier: "INFO",
    metadata: { tool_name: tool, analysis_phase: phase },
  } as unknown as AgentFindingDTO;
}

describe("dedupeAndFilter — no stale findings", () => {
  it("a deep finding supersedes the stale initial finding for the same tool", () => {
    const initial = finding(
      "neural_splicing",
      "POSITIVE",
      "initial",
      "Initial screen flagged a possible splice with confidence 0.59.",
    );
    const deep = finding(
      "neural_splicing",
      "INCONCLUSIVE",
      "deep",
      "Uncorroborated by the visual model; held inconclusive (likely a recompression artifact).",
    );

    const result = dedupeAndFilter([initial, deep]);

    expect(result).toHaveLength(1);
    expect(result[0].evidence_verdict).toBe("INCONCLUSIVE");
    expect(result[0].metadata?.analysis_phase).toBe("deep");
  });

  it("deep wins regardless of input ordering", () => {
    const initial = finding("neural_ela", "POSITIVE", "initial", "Initial ELA flagged anomaly region.");
    const deep = finding("neural_ela", "NEGATIVE", "deep", "Deep ELA pass found no manipulation anomaly.");

    const a = dedupeAndFilter([initial, deep]);
    const b = dedupeAndFilter([deep, initial]);

    expect(a[0].metadata?.analysis_phase).toBe("deep");
    expect(b[0].metadata?.analysis_phase).toBe("deep");
  });

  it("preserves every distinct backend finding (no silent drops)", () => {
    const findings = [
      finding("diffusion_artifact_detector", "NEGATIVE", "deep", "No diffusion/AI-generation artifacts detected in the image."),
      finding("neural_splicing", "INCONCLUSIVE", "deep", "Splicing screen uncorroborated by the visual model; held inconclusive."),
      finding("exif_extract", "NEGATIVE", "initial", "EXIF block parsed successfully with no provenance anomalies present."),
    ];

    const result = dedupeAndFilter(findings);

    expect(result).toHaveLength(3);
    expect(new Set(result.map((f) => f.metadata?.tool_name))).toEqual(
      new Set(["diffusion_artifact_detector", "neural_splicing", "exif_extract"]),
    );
  });
});
