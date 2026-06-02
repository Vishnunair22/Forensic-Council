import { supportedAgentIdsForMime, isAgentSupportedForMime } from "@/lib/agentSupport";

describe("supportedAgentIdsForMime (image-only contract)", () => {
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

  // Image-only contract: every active agent (Agent1/Agent3/Agent5) is image/
  // only per the backend AGENT_FILE_CAPABILITIES. Non-image types resolve to no
  // supported agent (the upload layer rejects them before analysis).
  it("routes audio/ types to no agent (image-only contract)", () => {
    const ids = supportedAgentIdsForMime("audio/wav");
    expect(ids).toEqual(new Set());
  });

  it("routes video/ types to no agent (image-only contract)", () => {
    const ids = supportedAgentIdsForMime("video/mp4");
    expect(ids).toEqual(new Set());
  });

  it("routes unknown types to no agent (image-only contract)", () => {
    const ids = supportedAgentIdsForMime("application/pdf");
    expect(ids).toEqual(new Set());
  });
});

describe("isAgentSupportedForMime (image-only contract)", () => {
  it("returns false for Agent3 with video/ (video not supported)", () => {
    expect(isAgentSupportedForMime("Agent3", "video/mp4")).toBe(false);
  });

  it("returns false for Agent3 with audio/", () => {
    expect(isAgentSupportedForMime("Agent3", "audio/wav")).toBe(false);
  });
});
