/*
 * Must stay in sync with backend AGENT_FILE_CAPABILITIES (apps/api/core/file_type_policy.py):
 *   Agent1 → image/
 *   Agent2 → (none — empty capabilities, currently disabled)
 *   Agent3 → image/
 *   Agent4 → (none — empty capabilities, currently disabled)
 *   Agent5 → image/
 *
 * When serverCapabilities are provided (fetched from GET /api/v1/capabilities),
 * those override the static mapping below.
 */

export type ServerCapabilities = {
  supported_mime_types: string[];
  max_file_size_bytes: number;
  agent_capabilities: Record<string, string[]>;
};

let _cachedCapabilities: ServerCapabilities | null = null;

export function setServerCapabilities(caps: ServerCapabilities): void {
  _cachedCapabilities = caps;
}

export function getServerCapabilities(): ServerCapabilities | null {
  return _cachedCapabilities;
}

export function supportedAgentIdsForMime(
  mimeType?: string | null,
  serverCapabilities?: ServerCapabilities | null,
): Set<string> {
  const caps = serverCapabilities ?? _cachedCapabilities;
  if (caps) {
    const result = new Set<string>();
    const normalized = (mimeType ?? "").toLowerCase();
    for (const [agentId, prefixes] of Object.entries(caps.agent_capabilities)) {
      if (prefixes.some((p) => normalized.startsWith(p))) {
        result.add(agentId);
      }
    }
    return result;
  }

  // Fallback static mapping (image-only per backend policy)
  if (!mimeType) return new Set(["Agent1", "Agent3", "Agent5"]);

  const normalized = mimeType.toLowerCase();
  if (normalized.startsWith("image/")) return new Set(["Agent1", "Agent3", "Agent5"]);
  return new Set(["Agent5"]);
}

export function isAgentSupportedForMime(
  agentId: string,
  mimeType?: string | null,
  serverCapabilities?: ServerCapabilities | null,
): boolean {
  return supportedAgentIdsForMime(mimeType, serverCapabilities).has(agentId);
}
