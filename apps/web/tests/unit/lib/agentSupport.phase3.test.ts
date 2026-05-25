import { supportedAgentIdsForMime, isAgentSupportedForMime } from "@/lib/agentSupport";

describe("supportedAgentIdsForMime (Phase 3 — edge cases)", () => {
  it("returns all non-Arbiter agents for undefined mimeType", () => {
    const ids = supportedAgentIdsForMime(undefined);
    expect(ids.has("Agent1")).toBe(true);
    expect(ids.has("Agent5")).toBe(true);
    expect(ids.has("Arbiter")).toBe(false);
    expect(ids.size).toBe(5);
  });

  it("returns all non-Arbiter agents for null mimeType", () => {
    const ids = supportedAgentIdsForMime(null);
    expect(ids.size).toBe(5);
  });

  it("routes image/ types to Agent1, Agent3, Agent5", () => {
    const ids = supportedAgentIdsForMime("image/png");
    expect(ids).toEqual(new Set(["Agent1", "Agent3", "Agent5"]));
  });

  it("routes audio/ types to Agent2, Agent5", () => {
    const ids = supportedAgentIdsForMime("audio/wav");
    expect(ids).toEqual(new Set(["Agent2", "Agent5"]));
  });

  it("routes video/ types to Agent2, Agent3, Agent4, Agent5", () => {
    const ids = supportedAgentIdsForMime("video/mp4");
    expect(ids).toEqual(new Set(["Agent2", "Agent3", "Agent4", "Agent5"]));
  });

  it("routes unknown types to Agent5 only", () => {
    const ids = supportedAgentIdsForMime("application/pdf");
    expect(ids).toEqual(new Set(["Agent5"]));
  });
});

describe("isAgentSupportedForMime (Phase 3)", () => {
  it("returns true for Agent3 with video/", () => {
    expect(isAgentSupportedForMime("Agent3", "video/mp4")).toBe(true);
  });

  it("returns false for Agent3 with audio/", () => {
    expect(isAgentSupportedForMime("Agent3", "audio/wav")).toBe(false);
  });
});
