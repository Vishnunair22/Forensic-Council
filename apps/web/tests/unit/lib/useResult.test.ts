import { buildAgentTimelineFromReport } from "@/hooks/useResult";
import type { ReportDTO } from "@/lib/api";

describe("buildAgentTimelineFromReport", () => {
  it("returns empty array when agent_summaries is undefined", () => {
    const report = { report_id: "r1", session_id: "s1", overall_verdict: "AUTHENTIC" } as ReportDTO;
    expect(buildAgentTimelineFromReport(report)).toEqual([]);
  });

  it("returns empty array when agent_summaries is null", () => {
    const report = {
      report_id: "r1", session_id: "s1", overall_verdict: "AUTHENTIC",
      agent_summaries: null,
    } as unknown as ReportDTO;
    expect(buildAgentTimelineFromReport(report)).toEqual([]);
  });

  it("extracts agent updates from agent_summaries", () => {
    const summaries = [
      { agent_id: "Agent1", agent_name: "Noise Analyzer", status: "complete", completed_at: "2025-06-01T12:00:00Z", message: "ELA complete" },
      { agent_id: "Agent3", agent_name: "Metadata Analyst", status: "complete", completed_at: "2025-06-01T12:01:00Z", message: "EXIF verified" },
    ];
    const report = {
      report_id: "r1", session_id: "s1", overall_verdict: "AUTHENTIC",
      agent_summaries: summaries,
    } as unknown as ReportDTO;

    const result = buildAgentTimelineFromReport(report);
    expect(result).toHaveLength(2);
    expect(result[0].agent_id).toBe("Agent1");
    expect(result[0].agent_name).toBe("Noise Analyzer");
    expect(result[1].agent_id).toBe("Agent3");
  });

  it("filters out summaries without agent_id", () => {
    const summaries = [
      { agent_name: "Ghost", status: "complete" },
      { agent_id: "Agent5", agent_name: "Coordinator", status: "complete" },
    ];
    const report = {
      report_id: "r1", session_id: "s1", overall_verdict: "AUTHENTIC",
      agent_summaries: summaries,
    } as unknown as ReportDTO;

    const result = buildAgentTimelineFromReport(report);
    expect(result).toHaveLength(1);
    expect(result[0].agent_id).toBe("Agent5");
  });

  it("defaults agent_name to agent_id when not provided", () => {
    const summaries = [
      { agent_id: "Agent3", status: "complete" },
    ];
    const report = {
      report_id: "r1", session_id: "s1", overall_verdict: "AUTHENTIC",
      agent_summaries: summaries,
    } as unknown as ReportDTO;

    const result = buildAgentTimelineFromReport(report);
    expect(result[0].agent_name).toBe("Agent3");
  });

  it("defaults status to 'complete' when not provided", () => {
    const summaries = [
      { agent_id: "Agent1" },
    ];
    const report = {
      report_id: "r1", session_id: "s1", overall_verdict: "AUTHENTIC",
      agent_summaries: summaries,
    } as unknown as ReportDTO;

    const result = buildAgentTimelineFromReport(report);
    expect(result[0].status).toBe("complete");
  });
});
