import { AGENTS as AGENTS_DATA } from "@/lib/constants";

export function supportedAgentIdsForMime(mimeType?: string | null): Set<string> {
  const allIds = new Set(AGENTS_DATA.filter((a) => a.id !== "Arbiter").map((a) => a.id));
  if (!mimeType) return allIds;

  const normalized = mimeType.toLowerCase();
  if (normalized.startsWith("image/")) return new Set(["Agent1", "Agent3", "Agent5"]);
  if (normalized.startsWith("audio/")) return new Set(["Agent2", "Agent5"]);
  if (normalized.startsWith("video/")) return new Set(["Agent2", "Agent3", "Agent4", "Agent5"]);

  return new Set(["Agent5"]);
}

export function isAgentSupportedForMime(agentId: string, mimeType?: string | null): boolean {
  return supportedAgentIdsForMime(mimeType).has(agentId);
}
