/*
 * Must stay in sync with backend AGENT_FILE_CAPABILITIES (apps/api/core/file_type_policy.py):
 *   Agent1 → image/
 *   Agent2 → audio/
 *   Agent3 → image/
 *   Agent4 → video/ (+ application/mp4)
 *   Agent5 → image/ audio/ video/ + application/pdf, application/mp4 (metadata — all types)
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
  // Only trust server capabilities when the agent_capabilities map is actually
  // present and well-formed; a partial/malformed capabilities object (missing
  // agent_capabilities) must fall through to the static mapping rather than
  // throw on Object.entries(undefined).
  if (caps && caps.agent_capabilities && typeof caps.agent_capabilities === "object") {
    const result = new Set<string>();
    const normalized = (mimeType ?? "").toLowerCase();
    for (const [agentId, prefixes] of Object.entries(caps.agent_capabilities)) {
      if (Array.isArray(prefixes) && prefixes.some((p) => normalized.startsWith(p))) {
        result.add(agentId);
      }
    }
    return result;
  }

  // Fallback static mapping — mirrors backend AGENT_FILE_CAPABILITIES so agent
  // filtering is correct even before server capabilities load (prevents the
  // race where audio/video files briefly show zero applicable agents).
  if (!mimeType) return new Set(["Agent1", "Agent3", "Agent5"]);

  const normalized = mimeType.toLowerCase();
  if (normalized.startsWith("image/")) return new Set(["Agent1", "Agent3", "Agent5"]);
  if (normalized.startsWith("audio/")) return new Set(["Agent2", "Agent5"]);
  if (normalized.startsWith("video/") || normalized === "application/mp4") {
    return new Set(["Agent4", "Agent5"]);
  }
  if (normalized === "application/pdf") return new Set(["Agent5"]);
  return new Set();
}

export function isAgentSupportedForMime(
  agentId: string,
  mimeType?: string | null,
  serverCapabilities?: ServerCapabilities | null,
): boolean {
  return supportedAgentIdsForMime(mimeType, serverCapabilities).has(agentId);
}
