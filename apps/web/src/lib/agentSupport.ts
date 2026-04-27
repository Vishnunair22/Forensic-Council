import { AGENTS as AGENTS_DATA } from "@/lib/constants";

export function supportedAgentIdsForMime(mimeType?: string | null): Set<string> {
  const allIds = new Set(AGENTS_DATA.filter((a) => a.id !== "Arbiter").map((a) => a.id));
  if (!mimeType) return allIds;
  if (mimeType.startsWith("image/")) return new Set(["Agent1", "Agent3", "Agent5"]);
  if (mimeType.startsWith("audio/")) return new Set(["Agent2", "Agent5"]);
  if (mimeType.startsWith("video/")) return new Set(["Agent3", "Agent4", "Agent5"]);
  return allIds;
}

export function isAgentSupportedForMime(agentId: string, mimeType?: string | null): boolean {
  return supportedAgentIdsForMime(mimeType).has(agentId);
}
