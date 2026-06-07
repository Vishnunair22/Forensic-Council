import { supportedAgentIdsForMime, isAgentSupportedForMime } from "@/lib/agentSupport";

describe("supportedAgentIdsForMime (multi-modal contract)", () => {
  it("routes undefined mimeType to Agent1, Agent3, Agent5 only", () => {
    const ids = supportedAgentIdsForMime(undefined);
    expect(ids.has("Agent1")).toBe(true);
    expect(ids.has("Agent3")).toBe(true);
    expect(ids.has("Agent5")).toBe(true);
    expect(ids.has("Arbiter")).toBe(false);
    expect(ids.size).toBe(3);
  });

  it("routes null mimeType to Agent1, Agent3, Agent5 only", () => {
    const ids = supportedAgentIdsForMime(null);
    expect(ids.size).toBe(3);
  });

  it("routes image/ types to Agent1, Agent3, Agent5", () => {
    const ids = supportedAgentIdsForMime("image/png");
    expect(ids).toEqual(new Set(["Agent1", "Agent3", "Agent5"]));
  });

  // Multi-modal contract — mirrors backend AGENT_FILE_CAPABILITIES:
  // audio → Agent2 + Agent5, video → Agent4 + Agent5, pdf → Agent5 (metadata).
  it("routes audio/ types to Agent2 + Agent5", () => {
    const ids = supportedAgentIdsForMime("audio/wav");
    expect(ids).toEqual(new Set(["Agent2", "Agent5"]));
  });

  it("routes video/ types to Agent4 + Agent5", () => {
    const ids = supportedAgentIdsForMime("video/mp4");
    expect(ids).toEqual(new Set(["Agent4", "Agent5"]));
  });

  it("routes application/pdf to Agent5 (metadata) only", () => {
    const ids = supportedAgentIdsForMime("application/pdf");
    expect(ids).toEqual(new Set(["Agent5"]));
  });

  it("routes a genuinely unknown type to no agent", () => {
    const ids = supportedAgentIdsForMime("application/x-tar");
    expect(ids).toEqual(new Set());
  });
});

describe("isAgentSupportedForMime (per-agent modality)", () => {
  it("returns false for Agent3 with video/ (video not supported)", () => {
    expect(isAgentSupportedForMime("Agent3", "video/mp4")).toBe(false);
  });

  it("returns false for Agent3 with audio/", () => {
    expect(isAgentSupportedForMime("Agent3", "audio/wav")).toBe(false);
  });
});
