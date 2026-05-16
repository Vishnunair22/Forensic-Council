/**
 * Shared agent visual identity — single source of truth referenced by
 * AgentStatusCard (live progress) and TimelineTab (history view), so the
 * same agent reads with the same accent color across the entire app.
 *
 * Token names mirror the CSS variables declared in globals.css under
 * "Agent accent tokens". Updating the palette = updating both files.
 */

export type AgentAccent = {
  /** CSS color expression suitable for `style={{ color: ... }}` */
  color: string;
  /** Tailwind-arbitrary background expression (low alpha) for icon containers */
  bgClass: string;
  /** Tailwind-arbitrary text-color expression for icon glyph */
  textClass: string;
};

export const AGENT_ACCENTS: Record<string, AgentAccent> = {
  Agent1: {
    color: "var(--color-agent-image)",
    bgClass: "bg-[var(--color-agent-image)]/10",
    textClass: "text-[var(--color-agent-image)]",
  },
  Agent2: {
    color: "var(--color-agent-audio)",
    bgClass: "bg-[var(--color-agent-audio)]/10",
    textClass: "text-[var(--color-agent-audio)]",
  },
  Agent3: {
    color: "var(--color-agent-scene)",
    bgClass: "bg-[var(--color-agent-scene)]/10",
    textClass: "text-[var(--color-agent-scene)]",
  },
  Agent4: {
    color: "var(--color-agent-video)",
    bgClass: "bg-[var(--color-agent-video)]/10",
    textClass: "text-[var(--color-agent-video)]",
  },
  Agent5: {
    color: "var(--color-agent-metadata)",
    bgClass: "bg-[var(--color-agent-metadata)]/10",
    textClass: "text-[var(--color-agent-metadata)]",
  },
  Arbiter: {
    color: "var(--color-success)",
    bgClass: "bg-[var(--color-success)]/10",
    textClass: "text-[var(--color-success)]",
  },
};

export function accentFor(agentId: string): AgentAccent {
  return AGENT_ACCENTS[agentId] ?? {
    color: "var(--color-primary)",
    bgClass: "bg-[var(--color-primary)]/10",
    textClass: "text-[var(--color-primary)]",
  };
}
