"use client";
/**
 * BOUNDARY: Owns SSE stream connection, agent update events, HITL checkpoint
 * state, arbiter live text, and reconnect logic.
 * Receives: sessionId from useInvestigation after upload succeeds.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { AGENTS as AGENTS_DATA } from "@/lib/constants";
import { storage, sessionOnlyStorage } from "@/lib/storage";
import { STORAGE_KEYS } from "@/lib/storageKeys";
import { clearInvestigationPersistence } from "@/lib/investigationStorage";

import { createLiveSocket, connectLiveSSE, BriefUpdate, HITLCheckpoint, getArbiterStatus, dbg, refreshAuthToken, autoLoginAsInvestigator } from "@/lib/api";
import { BriefUpdateSchema } from "@/lib/schemas";
import { toast } from "@/hooks/use-toast";
import { SoundType } from "./useSound";
import type { AgentUpdate } from "@/components/evidence/types";

class SessionGoneError extends Error {
  constructor() {
    super("Session no longer exists");
    this.name = "SessionGoneError";
  }
}

// Backend and Frontend share unified Agent IDs "Agent1"–"Agent5".

type SimulationStatus =
  | "idle"
  | "analyzing"
  | "initiating"
  | "processing"
  | "awaiting_decision"
  | "complete"
  | "error";

type SimulationPhase = "initial" | "deep";

type UseSimulationProps = {
  onAgentComplete?: (result: AgentUpdate) => void;
  onComplete?: () => void;
  playSound?: (type: SoundType) => void;
};

function getMessagePhase(update: BriefUpdate): "initial" | "deep" | null {
  const data = update.data as Record<string, unknown> | undefined;
  const phase = data?.analysis_phase;
  return phase === "initial" || phase === "deep" ? phase : null;
}

function getMessageSessionId(update: BriefUpdate, targetSessionId: string): string | null {
  const topLevel = update.session_id;
  if (typeof topLevel === "string") return topLevel;
  const data = update.data as Record<string, unknown> | undefined;
  const dataSessionId = typeof data?.session_id === "string" ? data.session_id : null;
  if (dataSessionId && dataSessionId !== targetSessionId) return null;
  return dataSessionId;
}

export const useSimulation = ({
  onAgentComplete,
  onComplete,
  playSound,
}: UseSimulationProps) => {
  const [status, setStatus] = useState<SimulationStatus>("idle");
  const [completedAgents, setCompletedAgents] = useState<AgentUpdate[]>([]);
  const [agentUpdates, setAgentUpdates] = useState<
    Record<
      string,
      {
        status: string;
        thinking: string;
        tools_done?: number;
        tools_total?: number;
        tool_name?: string;
      }
    >
  >({});
  const [hitlCheckpoint, setHitlCheckpoint] = useState<HITLCheckpoint | null>(
    null,
  );
  const [isDeepHITL, setIsDeepHITL] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [streamStalled, setStreamStalled] = useState(false);
  const [pipelineMessage, setPipelineMessage] = useState<string>("");
  const [pipelineThinking, setPipelineThinking] = useState<string>("");
  const [arbiterStatus, setArbiterStatus] = useState<string | null>(null);
  const [arbiterThinking, setArbiterThinking] = useState<string | null>(null);
  const [revealQueue] = useState<AgentUpdate[]>([]);
  const [revealPending] = useState(false);
  const activePhaseRef = useRef<SimulationPhase>("initial");

  const setSimulationPhase = useCallback((phase: SimulationPhase) => {
    activePhaseRef.current = phase;
  }, []);

  const wsRef = useRef<WebSocket | null>(null);
  const sseRef = useRef<{ close: () => void } | null>(null);
  const completedAgentsRef = useRef<AgentUpdate[]>([]);
  const lastMessageAtRef = useRef<number>(0);
  const stallTimerRef = useRef<NodeJS.Timeout | null>(null);
  const lastSessionIdRef = useRef<string | null>(null);
  /** True after POST /resume succeeds — PIPELINE_COMPLETE must not be dropped while still `awaiting_decision` from React's stale batch. */
  const expectingPipelineCompleteRef = useRef(false);
  /** Guards against firing the complete sound/callback more than once per session (stale-closure-safe). */
  const hasFiredCompleteRef = useRef(false);
  /** Tracks pending reconnect delay timer so it can be cancelled on unmount. */
  const reconnectTimerRef = useRef<NodeJS.Timeout | null>(null);

  // WebSocket reconnection config with exponential backoff
  const reconnectConfig = useRef({
    initialDelay: 1000,
    maxDelay: 5000,
    backoffFactor: 2,
    maxRetries: 12,
  });
  const reconnectAttemptsRef = useRef(0);
  const authRetryAttemptsRef = useRef<Record<string, number>>({});
  const arbiterPollRef = useRef<NodeJS.Timeout | null>(null);
  /** Guards async poll callbacks from setting state after the component unmounts. */
  const isMountedRef = useRef(true);

  // Store callbacks in refs to avoid triggering effect on every render
  const onAgentCompleteRef = useRef(onAgentComplete);
  const onCompleteRef = useRef(onComplete);
  const playSoundRef = useRef(playSound);

  // Update refs when props change
  useEffect(() => {
    onAgentCompleteRef.current = onAgentComplete;
    onCompleteRef.current = onComplete;
    playSoundRef.current = playSound;
  }, [onAgentComplete, onComplete, playSound]);

  // Connect WebSocket manually — returns a Promise that resolves once the WS is open.
  const connectWebSocket = useCallback(
    (targetSessionId: string, isReconnect: boolean = false): Promise<void> => {
      // Hard-clear completedAgents when session ID changes
      if (lastSessionIdRef.current !== null && lastSessionIdRef.current !== targetSessionId) {
        setCompletedAgents([]);
        completedAgentsRef.current = [];
        setAgentUpdates({});
        setPipelineMessage("");
        setPipelineThinking("");
      }
      lastSessionIdRef.current = targetSessionId;

      // Store session ID
      setSessionId(targetSessionId);

      if (!isReconnect) {
        // Only reset state for a brand new investigation
        setStatus("initiating");
        setCompletedAgents([]);
        completedAgentsRef.current = [];
        setAgentUpdates({});
        setErrorMessage(null);
      }

      return new Promise((resolve, reject) => {
        // Disconnect existing
        if (wsRef.current) {
          wsRef.current.close();
          wsRef.current = null;
        }
        if (sseRef.current) {
          sseRef.current.close();
          sseRef.current = null;
        }

        // Use a persistent queue ref to avoid concurrent processing loops on reconnect
        const messageQueue: BriefUpdate[] = [];
        let isProcessingQueue = false;
        let wsConnectionReady = false;

        let isActive = true;

        const applyUpdate = (update: BriefUpdate) => {
          if (process.env.NODE_ENV === 'development') {
            console.log('[WS Update]', {
              type: update.type,
              agent_id: update.agent_id,
              phase: getMessagePhase(update),
              activePhase: activePhaseRef.current,
              data: update.data,
            });
          }

          const incomingSessionId = getMessageSessionId(update, targetSessionId);
          if (incomingSessionId && incomingSessionId !== targetSessionId) {
            dbg.warn("[WebSocket] Ignoring update for non-current session", {
              current: targetSessionId,
              incoming: incomingSessionId,
              type: update.type,
            });
            return;
          }

          const messagePhase = getMessagePhase(update);
          const allowedCrossPhaseTypes = new Set([
            "PIPELINE_PAUSED", "ARBITER_UPDATE", "REPORT_READY", "CONNECTED", "HITL_CHECKPOINT",
          ]);
          if (messagePhase && messagePhase !== activePhaseRef.current) {
            if (!allowedCrossPhaseTypes.has(update.type)) {
              dbg.log("[WebSocket] Ignoring stale phase message", {
                active: activePhaseRef.current,
                incoming: messagePhase,
                type: update.type,
              });
              return;
            }
          }

          if (
            activePhaseRef.current === "deep" &&
            update.type === "AGENT_COMPLETE" &&
            update.data?.analysis_phase === "initial"
          ) {
            dbg.log("[WebSocket] Ignoring initial-phase AGENT_COMPLETE during deep analysis");
            return;
          }

          if (
            activePhaseRef.current === "initial" &&
            update.type === "AGENT_COMPLETE" &&
            update.data?.analysis_phase === "deep"
          ) {
            dbg.log("[WebSocket] Ignoring deep-phase AGENT_COMPLETE during initial analysis");
            return;
          }

          switch (update.type) {
            case "CONNECTED":
                    // Server confirmed auth and registered socket — connection fully ready.
                    // No UI action needed; the connected promise is already resolved in api.ts.
                    break;

                  case "AGENT_UPDATE":
                  // Phase guard: drop updates that carry a phase marker
                  // that does not match the active analysis phase.
                  {
                    const updatePhase = getMessagePhase(update);
                    if (updatePhase && updatePhase !== activePhaseRef.current) {
                      dbg.log("[WebSocket] Ignoring stale-phase AGENT_UPDATE", {
                        active: activePhaseRef.current,
                        incoming: updatePhase,
                        agent_id: update.agent_id,
                      });
                      break;
                    }
                  }
                  // Pipeline-level updates come through with agent_id=null.
                  // Surface them separately so the UI can show "what the backend is doing" in real time.
                  if (!update.agent_id) {
                    setPipelineMessage(update.message || "");
                    const t = (update.data as Record<string, unknown> | null)?.[
                      "thinking"
                    ];
                    setPipelineThinking(
                      typeof t === "string" ? t : update.message || "",
                    );
                    // Transition to "analyzing" from either "idle" or "initiating"
                    // (status is never set to "initiating" externally; it starts as "idle")
                    setStatus((prev: SimulationStatus) =>
                      prev === "idle" || prev === "initiating" ? "analyzing" : prev,
                    );
                    break;
                  }
                  if (update.agent_id && update.data) {
                    const agentData = update.data as {
                      status?: string;
                      thinking?: string;
                      tools_done?: number;
                      tools_total?: number;
                      tool_name?: string;
                    };
                    const incomingId = update.agent_id ?? "";

                    setAgentUpdates(
                      (
                        prev: Record<
                          string,
                          {
                            status: string;
                            thinking: string;
                            tools_done?: number;
                            tools_total?: number;
                            tool_name?: string;
                          }
                        >,
                      ) => ({
                        ...prev,
                        [incomingId]: {
                          status: agentData.status || "running",
                          // Preserve the last non-empty thinking so agent cards never
                          // flip to the pipeline-level fallback between tool executions.
                          thinking:
                            (agentData.thinking?.trim()
                              ? agentData.thinking
                              : prev[incomingId]?.thinking) ?? "",
                          tools_done:
                            typeof agentData.tools_done === "number"
                              ? agentData.tools_done
                              : prev[incomingId]?.tools_done,
                          tools_total:
                            typeof agentData.tools_total === "number"
                              ? agentData.tools_total
                              : prev[incomingId]?.tools_total,
                          tool_name:
                            typeof agentData.tool_name === "string"
                              ? agentData.tool_name
                              : prev[incomingId]?.tool_name,
                        },
                      }),
                    );
                    // Transition to "analyzing" from either "idle" or "initiating"
                    setStatus((prev: SimulationStatus) =>
                      prev === "idle" || prev === "initiating" ? "analyzing" : prev,
                    );
                  }
                  break;

                case "HITL_CHECKPOINT":
                  if (update.data) {
                    // Backend nests the id under data.checkpoint.id; fall back to
                    // flat data.checkpoint_id for forward-compatibility.
                    const _hitlData = update.data as {
                      checkpoint?: { id?: string };
                      checkpoint_id?: string;
                    };
                    const checkpoint: HITLCheckpoint = {
                      checkpoint_id: _hitlData.checkpoint?.id ?? _hitlData.checkpoint_id ?? "",
                      session_id: update.session_id,
                      agent_id: update.agent_id ?? "",
                      agent_name: update.agent_name || "",
                      brief_text: update.message,
                      decision_needed: "APPROVE, REDIRECT, or TERMINATE",
                      created_at: new Date().toISOString(),
                    };
                    // Persist to storage so the modal survives a page refresh
                    try { storage.setItem(STORAGE_KEYS.HITL_CHECKPOINT, checkpoint, true); } catch (e) { dbg.warn("[Simulation] HITL checkpoint persist failed:", e); }
                    setHitlCheckpoint(checkpoint);
                  }
                  break;

                case "HITL_EXPIRED":
                  setHitlCheckpoint(null);
                  try { storage.removeItem(STORAGE_KEYS.HITL_CHECKPOINT); } catch (e) { dbg.warn("[Simulation] HITL checkpoint clear failed:", e); }
                  break;

                case "AGENT_COMPLETE":
                  if (update.agent_id) {
                    const normalizedCompleteId = update.agent_id;
                    const agent = AGENTS_DATA.find(
                      (a) => a.id === normalizedCompleteId,
                    );
                    if (agent) {
                      const {
                        confidence,
                        findings_count,
                        error,
                        deep_analysis_pending,
                        status: agentStatus,
                        agent_verdict,
                        summary,
                        tool_error_rate,
                        section_flags,
                        findings_preview,
                        tools_ran,
                        tools_skipped,
                        tools_failed,
                        degraded,
                        verdict_score,
                        image_context,
                      } = update.data as Record<string, unknown>;
                      const previewConfidenceValues = Array.isArray(findings_preview)
                        ? findings_preview
                            .map((item) =>
                              item &&
                              typeof item === "object" &&
                              "confidence" in item &&
                              typeof (item as { confidence?: unknown }).confidence === "number"
                                ? (item as { confidence: number }).confidence
                                : null,
                            )
                            .filter((value): value is number => typeof value === "number")
                        : [];
                      const parsedConfidence =
                        (typeof confidence === "number" ? confidence : null) ??
                        (previewConfidenceValues.length > 0
                          ? previewConfidenceValues.reduce((sum, value) => sum + value, 0) / previewConfidenceValues.length
                          : 0);

                      const newUpdate: AgentUpdate = {
                        agent_id: agent.id,
                        agent_name: update.agent_name || agent.name,
                        message: update.message || "Analysis complete",
                        status:
                          (typeof agentStatus === "string"
                            ? (agentStatus as AgentUpdate["status"])
                            : null) || "complete",
                        confidence: parsedConfidence,
                        findings_count:
                          typeof findings_count === "number"
                            ? findings_count
                            : 1,
                        error: typeof error === "string" ? error : undefined,
                        deep_analysis_pending:
                          typeof deep_analysis_pending === "boolean"
                            ? deep_analysis_pending
                            : undefined,
                        agent_verdict:
                          typeof agent_verdict === "string"
                            ? (agent_verdict as AgentUpdate["agent_verdict"])
                            : undefined,
                        summary: typeof summary === "string" ? summary : undefined,
                        tool_error_rate:
                          typeof tool_error_rate === "number"
                            ? tool_error_rate
                            : undefined,
                        section_flags: Array.isArray(section_flags)
                          ? (section_flags as AgentUpdate["section_flags"])
                          : undefined,
                        findings_preview: Array.isArray(findings_preview)
                          ? (findings_preview as AgentUpdate["findings_preview"])
                          : undefined,
                        tools_ran:
                          typeof tools_ran === "number" ? tools_ran : undefined,
                        tools_skipped:
                          typeof tools_skipped === "number"
                            ? tools_skipped
                            : undefined,
                        tools_failed:
                          typeof tools_failed === "number"
                            ? tools_failed
                            : undefined,
                        degraded: typeof degraded === "boolean" ? degraded : undefined,
                        verdict_score:
                          typeof verdict_score === "number"
                            ? verdict_score
                            : undefined,
                        image_context: typeof image_context === "string" ? image_context : undefined,
                        completed_at: new Date().toISOString(),
                      };

                      setAgentUpdates((prev) => ({
                        ...prev,
                        [agent.id]: {
                          status: newUpdate.status,
                          thinking: newUpdate.message,
                          tools_done:
                            typeof newUpdate.tools_ran === "number"
                              ? newUpdate.tools_ran
                              : prev[agent.id]?.tools_done,
                          tools_total:
                            typeof newUpdate.tools_ran === "number"
                              ? newUpdate.tools_ran
                              : prev[agent.id]?.tools_total,
                          tool_name: prev[agent.id]?.tool_name,
                        },
                      }));

                      // Upsert by agent_id — replace entirely so deep-phase findings
                      // are never contaminated with initial-phase data.
                      const existingIndex =
                        completedAgentsRef.current.findIndex(
                          (a: AgentUpdate) => a.agent_id === newUpdate.agent_id,
                        );
                      // Was this agent already marked complete? If so, this is a
                      // replayed AGENT_COMPLETE (WS reconnect replays the whole
                      // buffer with no Last-Event-ID cursor) — upsert the data but
                      // suppress the one-shot side effects (sound + callback) so
                      // they don't fire again per reconnect.
                      const isReplayComplete = existingIndex >= 0;
                      if (existingIndex >= 0) {
                        completedAgentsRef.current[existingIndex] = newUpdate;
                      } else {
                        completedAgentsRef.current.push(newUpdate);
                      }

                      const completedUpdate = completedAgentsRef.current[
                        existingIndex >= 0 ? existingIndex : completedAgentsRef.current.length - 1
                      ];
                      setCompletedAgents((current) => {
                        const exists = current.some((a) => a.agent_id === completedUpdate.agent_id);
                        if (exists) {
                          return current.map((a) =>
                            a.agent_id === completedUpdate.agent_id ? completedUpdate : a,
                          );
                        }
                        return [...current, completedUpdate];
                      });
                      if (!isReplayComplete) {
                        playSoundRef.current?.("agent");
                        onAgentCompleteRef.current?.(completedUpdate);
                      }

                      // Also transition to analyzing if still idle or initiating
                      setStatus((prev: SimulationStatus) =>
                        prev === "idle" || prev === "initiating" ? "analyzing" : prev,
                      );
                    }
                  }
                  break;

                case "AGENT_GROUNDED": {
                  // Reconcile a completed card to the arbiter-grounded verdict the
                  // signed report will use (single source of truth). PARTIAL merge:
                  // update only verdict + confidence, preserving findings_preview,
                  // tools and other per-agent data the AGENT_COMPLETE event carried.
                  if (update.agent_id) {
                    const groundedId = update.agent_id;
                    const gData = (update.data || {}) as Record<string, unknown>;
                    const gVerdict = gData.agent_verdict;
                    const gConf = gData.confidence;
                    const applyGrounding = (a: AgentUpdate): AgentUpdate => ({
                      ...a,
                      agent_verdict:
                        typeof gVerdict === "string"
                          ? (gVerdict as AgentUpdate["agent_verdict"])
                          : a.agent_verdict,
                      confidence: typeof gConf === "number" ? gConf : a.confidence,
                    });
                    const gIdx = completedAgentsRef.current.findIndex(
                      (a: AgentUpdate) => a.agent_id === groundedId,
                    );
                    if (gIdx >= 0) {
                      completedAgentsRef.current[gIdx] = applyGrounding(
                        completedAgentsRef.current[gIdx],
                      );
                      setCompletedAgents((current) =>
                        current.map((a) =>
                          a.agent_id === groundedId ? applyGrounding(a) : a,
                        ),
                      );
                    }
                  }
                  break;
                }

                case "INITIAL_ANALYSIS_COMPLETE":
                  // Informational marker emitted immediately before PIPELINE_PAUSED.
                  // The awaiting-decision transition is driven by PIPELINE_PAUSED, so no
                  // state change is needed here; this explicit case keeps the event
                  // contract complete and avoids the default "unhandled event" warning.
                  break;

                case "PIPELINE_PAUSED":
                  setStatus("awaiting_decision");
                  setIsDeepHITL(
                    (update.data as Record<string, unknown> | undefined)
                      ?.status === "awaiting_deep_report",
                  );
                  // No sound here: the "analysis_done" arpeggio is fired by the
                  // awaitingDecision effect in useInvestigation, synced to the
                  // decision gate actually appearing. Firing "think" here too
                  // produced a double sound for the same transition.
                  break;

                case "PIPELINE_COMPLETE":
                  // F-9: always transition to complete on PIPELINE_COMPLETE — the
                  // pipeline may have timed out the HITL gate, in which case the
                  // frontend would be stuck on awaiting_decision forever.  The only
                  // exception is when React's stale batch still reports
                  // awaiting_decision right after resumeInvestigation() — in that
                  // case expectingPipelineCompleteRef.current is true and we honour
                  // the transition.
                  expectingPipelineCompleteRef.current = false;
                  if (arbiterPollRef.current) {
                    clearInterval(arbiterPollRef.current);
                    arbiterPollRef.current = null;
                  }
                  if (!hasFiredCompleteRef.current) {
                    hasFiredCompleteRef.current = true;
                    playSoundRef.current?.("complete");
                    onCompleteRef.current?.();
                  }
                  setStatus("complete");
                  break;

                case "ERROR":
                  dbg.error("[WebSocket] Error:", update.message);
                  expectingPipelineCompleteRef.current = false;
                  setErrorMessage(update.message || "Investigation failed");
                  setStatus("error");
                  break;

                case "PIPELINE_QUARANTINED":
                  dbg.error("[WebSocket] Pipeline quarantined:", update.message);
                  expectingPipelineCompleteRef.current = false;
                  setErrorMessage(
                    update.message ||
                      "CRITICAL: Investigation pipeline quarantined — forensic violation detected.",
                  );
                  setStatus("error");
                  playSoundRef.current?.("error");
                  break;

                case "REPORT_READY":
                  dbg.log("[WebSocket] Report ready:", update.data);
                  if (update.data?.report_id) {
                    setStatus((prev) =>
                      prev === "complete" || prev === "error" ? prev : "complete"
                    );
                    onCompleteRef.current?.();
                  }
                  break;

                case "ARBITER_UPDATE":
                  if (update.data) {
                    const arbData = update.data as { status?: string; thinking?: string };
                    setArbiterStatus(arbData.status || "processing");
                    setArbiterThinking(arbData.thinking || update.message);
                  }
                  break;

                case "BATCH":
                  if (Array.isArray((update as { updates?: unknown }).updates)) {
                    for (const u of (update as { updates: BriefUpdate[] }).updates) {
                      applyUpdate(u);
                    }
                  }
                  break;

                case "DEGRADED":
                  toast.warning({
                    title: "Analysis Degraded",
                    description: update.message || "Some forensic capabilities are unavailable. Results may be limited.",
                  });
                  break;

                default:
                  dbg.warn("[WebSocket] Unhandled event type:", update.type);
                  break;
          }
        };

        const processQueue = async () => {
          if (isProcessingQueue || messageQueue.length === 0) return;
          isProcessingQueue = true;

          try {
            while (messageQueue.length > 0 && isActive) {
              const update = messageQueue.shift();
              if (!update) break;

              dbg.log("[Simulation] Processing update from queue:", update);

              try {
                applyUpdate(update);
              } catch (applyErr) {
                console.error("[Simulation] applyUpdate failed:", applyErr);
                dbg.warn("[Simulation] applyUpdate failed:", applyErr);
              }
            }
          } finally {
            isProcessingQueue = false;
          }
        };

        const handleMessage = (event: MessageEvent) => {
          try {
            const raw = JSON.parse(event.data);
            const parsed = BriefUpdateSchema.safeParse(raw);
            if (!parsed.success) {
              dbg.warn("[WebSocket] Message failed schema validation — using raw:", parsed.error.message);
            }
            const update: BriefUpdate = (parsed.success ? parsed.data : raw) as BriefUpdate;

            // Respond to server keepalive pings so the idle monitor stays reset.
            if ((update as { type: string }).type === "PING") {
              wsRef.current?.send(JSON.stringify({ type: "PONG", timestamp: Date.now() }));
              lastMessageAtRef.current = Date.now();
              setStreamStalled(false);
              return;
            }

            lastMessageAtRef.current = Date.now();
            setStreamStalled(false);

            dbg.log("[WebSocket] Received update, adding to queue:", update);

            // Only true terminal/error events jump to the front of the queue.
            // PIPELINE_PAUSED and HITL_CHECKPOINT must NOT skip ahead of
            // already-queued AGENT_COMPLETE events — doing so causes the UI to
            // transition to awaiting_decision before any agent cards are populated.
            const shouldJumpQueue = [
              "PIPELINE_COMPLETE",
              "ERROR",
              "PIPELINE_QUARANTINED",
            ].includes(update.type);
            // Proactive trim: keep queue under limit BEFORE pushing so
            // high-throughput bursts cannot accumulate thousands of items.
            const MAX_QUEUE = 500;
            while (messageQueue.length >= MAX_QUEUE) {
              const dropIdx = messageQueue.findIndex(
                (m) =>
                  ![
                    "PIPELINE_COMPLETE",
                    "ERROR",
                    "PIPELINE_PAUSED",
                    "HITL_CHECKPOINT",
                    "HITL_EXPIRED",
                    "PIPELINE_QUARANTINED",
                  ].includes(m.type),
              );
              if (dropIdx >= 0) {
                messageQueue.splice(dropIdx, 1);
              } else {
                messageQueue.shift();
              }
            }
            if (shouldJumpQueue) {
              messageQueue.unshift(update);
            } else {
              messageQueue.push(update);
            }
            processQueue();
          } catch (error) {
            dbg.error("[WebSocket] Failed to parse message:", error);
          }
        };

        // Create socket and get the connection promise
        const { ws, connected } = createLiveSocket(targetSessionId);
        // Suppress unhandled rejection warning if the socket closes before we attach the real handler.
        connected.catch(() => {});
        wsRef.current = ws;

        // Add 15s connection timeout for WebSocket
        const connectionTimeoutPromise = new Promise<void>((_, reject) => {
          const timeoutId = setTimeout(() => {
            ws.close();
            reject(new Error("WebSocket connection timeout (15s)"));
          }, 15000);
          connected.finally(() => clearTimeout(timeoutId));
        });
        const racedConnection = Promise.race([connected, connectionTimeoutPromise]);

        // Wire up message handler.
        // createLiveSocket attaches a bootstrap listener via addEventListener (to resolve 'connected').
        // Use addEventListener here too so both handlers fire independently and neither overwrites the other.
        ws.addEventListener("message", handleMessage);

        // Handle close - reject if closed before/during connection, otherwise notify
        const handleClose = (event: CloseEvent) => {
          isActive = false;
          dbg.log("[WebSocket] Connection closed:", event.code, event.reason);
          wsRef.current = null;

          // ── Terminal Close Codes ──────────────────────────────────────────
          // If the server tells us the session is dead, unauthorized, or missing,
          // we must clear our local storage and NOT attempt a reconnect.
          // 4001: Missing session ID / Invalid path
          // 4003: Access Denied (Identity Mismatch)
          // 4004: Session Not Found
          // 4010: Session Interrupted (Poisoned by restart or terminal error)
          // C-M-5: 1011 (server error) and 1013 (try again later, broker
          // saturated) are added so we don't loop reconnect-attempts
          // through a server that explicitly told us the channel is
          // dead/busy.
          const closeCodeMessages: Record<number, string> = {
            4001: "Authentication failed. Please refresh the page.",
            4003: "You do not have access to this investigation.",
            4004: "Investigation session not found. It may have expired.",
            4010: "Investigation interrupted by server restart. Please start a new analysis.",
            1011: "Server error. Please refresh and try again.",
            1013: "Server is temporarily unavailable. Please try again later.",
          };
          const friendlyMessage = closeCodeMessages[event.code] || event.reason || "Investigation interrupted. Please restart.";

          if (event.code === 4001) {
            const retries = authRetryAttemptsRef.current[targetSessionId] || 0;
            if (retries < 1) {
              authRetryAttemptsRef.current[targetSessionId] = retries + 1;
              dbg.log("[WebSocket] Auth failed (4001). Refreshing token and retrying connection once...");
              setIsReconnecting(true);
              (async () => {
                try {
                  const refreshSuccess = await refreshAuthToken();
                  if (!refreshSuccess) {
                    await autoLoginAsInvestigator();
                  }
                  const currentSessionId = storage.getItem(STORAGE_KEYS.SESSION_ID);
                  if (currentSessionId === targetSessionId) {
                    connectWebSocket(currentSessionId, isReconnect)
                      .then(() => resolve())
                      .catch((err) => reject(err));
                  } else {
                    reject(new Error("Session changed during re-authentication."));
                  }
                } catch (reauthErr) {
                  dbg.warn("[WebSocket] Re-auth failed during 4001 recovery:", reauthErr);
                  setIsReconnecting(false);
                  setSessionId(null);
                  clearInvestigationPersistence();
                  if (wsConnectionReady) {
                    setErrorMessage(friendlyMessage);
                    setStatus("error");
                  }
                  if (!wsConnectionReady) {
                    reject(new Error(friendlyMessage));
                  }
                }
              })();
              return;
            }
          }

          const terminalCodes = [1011, 1013, 4001, 4003, 4004, 4010];
          if (terminalCodes.includes(event.code)) {
            dbg.warn("[WebSocket] Terminal close code received. Clearing session state.");
            setIsReconnecting(false);
            setSessionId(null);
            clearInvestigationPersistence();

            // If connection was already established, set to error state
            if (wsConnectionReady) {
              setErrorMessage(friendlyMessage);
              setStatus("error");
            }
            // Reject the pending promise if it hasn't resolved
            if (!wsConnectionReady) {
              reject(new Error(friendlyMessage));
            }
            return;
          }

          // If connection was never established, reject the promise
          if (!wsConnectionReady) {
            const reason =
              event.reason || `Connection failed (code ${event.code})`;
            reject(new Error(reason));
            return;
          }

          // Connection was established but closed - attempt reconnection with exponential backoff
          setStatus((prev: SimulationStatus) => {
            if (prev !== "complete" && prev !== "error" && prev !== "idle") {
              if (expectingPipelineCompleteRef.current) {
                return prev;
              }
              if (reconnectAttemptsRef.current < reconnectConfig.current.maxRetries) {
                // C-L-2: full-jitter backoff so N clients re-connecting
                // after a backend restart don't synchronize into a
                // thundering herd. delay = random in [base/2, base].
                const rawDelay = Math.min(
                  reconnectConfig.current.initialDelay *
                    Math.pow(reconnectConfig.current.backoffFactor, reconnectAttemptsRef.current),
                  reconnectConfig.current.maxDelay,
                );
                const delay = Math.round(rawDelay * (0.5 + Math.random() * 0.5));
                reconnectAttemptsRef.current++;
                setIsReconnecting(true);
                if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
                reconnectTimerRef.current = setTimeout(() => {
                  reconnectTimerRef.current = null;
                  const currentSessionId = storage.getItem(STORAGE_KEYS.SESSION_ID);
                  if (currentSessionId === targetSessionId) {
                    connectWebSocket(currentSessionId, true).catch(() => {});
                  }
                }, delay);
                return prev;
              } else {
                setIsReconnecting(false);
                setErrorMessage("Connection lost. Please refresh the page.");
                return "error";
              }
            }
            return prev;
          });
        };
        // Use addEventListener so we don't override the onclose set in createLiveSocket
        // (which is responsible for clearing the connection timeout and settling the
        // `connected` promise). Both handlers will fire in order when the socket closes.
        ws.addEventListener("close", handleClose);

        // Wait for connection - resolve or reject based on outcome.
        // On success (including reconnects) rehydrate state from the arbiter status
        // endpoint so missed WS messages during the gap don't leave the UI stale.
        racedConnection
          .then(async () => {
            wsConnectionReady = true;
            reconnectAttemptsRef.current = 0; // Reset backoff on successful connect
            setIsReconnecting(false);
            resolve();
            // Rehydrate: if the arbiter reached a terminal state while the socket
            // was down, catch up immediately. The arbiter-status endpoint returns
            // "complete" | "error" | "running" | "not_found" — never "awaiting_decision"
            // (that transition is WS-only via PIPELINE_PAUSED and is implicitly
            // restored by the HITL checkpoint sessionStorage key above).
            try {
              const currentSid = targetSessionId || storage.getItem(STORAGE_KEYS.SESSION_ID);
              if (currentSid) {
                const st = await getArbiterStatus(currentSid);
                if (st.status === "complete") {
                  // F-H-4: do NOT trample awaiting_decision on reconnect. If the
                  // user is mid-Accept/Deep decision, the WS rehydrate path must
                  // not yank them into the result page. Only flip to "complete"
                  // when status is already processing (resume in flight) or when
                  // expectingPipelineCompleteRef was previously set.
                  setStatus((prev: SimulationStatus) => {
                    if (
                      prev === "awaiting_decision" &&
                      !expectingPipelineCompleteRef.current
                    ) {
                      return prev;
                    }
                    expectingPipelineCompleteRef.current = true;
                    return "complete";
                  });
                } else if (st.status === "error") {
                  setErrorMessage(st.message || "Investigation failed");
                  setStatus("error");
                }
                // "running" / "not_found": keep current status; WS will deliver updates
              }
            } catch {
              // Non-fatal — the live WS stream will update state normally
            }
          })
          .catch((err: unknown) => {
            // connected promise settled (either onerror or onclose before open)
            if (!wsConnectionReady) {
              dbg.warn("[WebSocket] Connection failed, falling back to SSE progress stream...", err);
              toast.warning({
                title: "Live Feed Degraded",
                description: "Direct WebSocket connection failed. Falling back to Server-Sent Events (SSE). UI updates may be slightly delayed.",
              });
              try {
                if (wsRef.current) {
                  wsRef.current.close();
                  wsRef.current = null;
                }
                const sseConnection = connectLiveSSE(
                  targetSessionId,
                  (data) => {
                    const update = data as BriefUpdate;
                    if ((update as { type: string }).type === "PING") {
                      return;
                    }
                    messageQueue.push(update);
                    processQueue();
                  },
                  (sseErr) => {
                    dbg.warn("[SSE] Reconnection error:", sseErr.message);
                  }
                );
                sseRef.current = sseConnection;
                wsConnectionReady = true;
                setIsReconnecting(false);
                resolve();
              } catch {
                const msg = err instanceof Error ? err.message : "WebSocket connection failed";
                reject(new Error(msg));
              }
            }
          });
      });
    },
    // connectWebSocket intentionally has empty deps.
    // All state is accessed via refs (completedAgentsRef, playSoundRef, etc.)
    // to avoid re-creating the socket on every state change.
    // DO NOT add state dependencies here without thinking carefully.
    [],
  );

  // Stream-stall detector: fires when no WS/SSE message arrives for 30 s
  // while the pipeline is actively running.  Exposed as `streamStalled` so the
  // UI can surface a "Stream stalled – try refreshing" nudge.
  useEffect(() => {
    const STALL_MS = 30_000;
    const activeStatuses: string[] = ["analyzing", "initiating", "processing"];
    if (!activeStatuses.includes(status)) {
      if (stallTimerRef.current) {
        clearTimeout(stallTimerRef.current);
        stallTimerRef.current = null;
      }
      setStreamStalled(false);
      return;
    }

    const schedule = () => {
      if (stallTimerRef.current) clearTimeout(stallTimerRef.current);
      stallTimerRef.current = setTimeout(() => {
        if (isMountedRef.current) setStreamStalled(true);
      }, STALL_MS);
    };

    schedule();
    return () => {
      if (stallTimerRef.current) {
        clearTimeout(stallTimerRef.current);
        stallTimerRef.current = null;
      }
    };
  }, [status]);

  // Cleanup WebSocket on unmount only.
  // IMPORTANT: This must NOT depend on sessionId — if it did, the cleanup would
  // fire every time connectWebSocket calls setSessionId(), killing the newly
  // created socket before it can connect (WebSocket closed before established).
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (stallTimerRef.current) {
        clearTimeout(stallTimerRef.current);
        stallTimerRef.current = null;
      }
      if (arbiterPollRef.current) {
        clearInterval(arbiterPollRef.current);
        arbiterPollRef.current = null;
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      if (sseRef.current) {
        sseRef.current.close();
        sseRef.current = null;
      }
    };
  }, []);

  // Token expiry checker — reschedules when session changes, but does NOT
  // touch the WebSocket (that lives in the unmount-only effect above).
  useEffect(() => {
    let tokenExpiryTimeout: NodeJS.Timeout;
    const scheduleTokenExpiryCheck = () => {
      const expiryStr = sessionOnlyStorage.getItem(STORAGE_KEYS.AUTH_TOKEN_EXPIRY);
      if (!expiryStr) return;
      const expiry = parseInt(expiryStr);
      const now = Date.now();
      const timeToExpiry = expiry - now;
      const checkDelay = Math.max(0, timeToExpiry - 30000);

      tokenExpiryTimeout = setTimeout(() => {
        // Token expires soon — attempt refresh via the shared API client so 401
        // triggers the session-expired redirect instead of silently failing.
        refreshAuthToken().then((ok) => {
          if (!ok) {
            sessionOnlyStorage.removeItem(STORAGE_KEYS.AUTH_TOKEN_EXPIRY);
            setErrorMessage("Session refresh failed. Re-authentication will be attempted on the next request.");
            return;
          }
          const currentSessionId = sessionId || storage.getItem(STORAGE_KEYS.SESSION_ID);
          if (currentSessionId) {
            connectWebSocket(currentSessionId, true);
          }
          scheduleTokenExpiryCheck();
        });
      }, checkDelay);
    };
    scheduleTokenExpiryCheck();

    return () => {
      clearTimeout(tokenExpiryTimeout);
    };
  }, [sessionId, connectWebSocket]);

  // Restore any pending HITL checkpoint that survived a page refresh
  useEffect(() => {
    try {
      // Only restore HITL checkpoint if this is a genuine reconnect,
      // not a fresh upload initiated from the home page
      const isFreshUpload = sessionOnlyStorage.getItem(STORAGE_KEYS.AUTO_START) === "true" ||
                            sessionOnlyStorage.getItem(STORAGE_KEYS.FC_HANDOFF_FIRED) === "1";
      if (isFreshUpload) {
        storage.removeItem(STORAGE_KEYS.HITL_CHECKPOINT);
        return;
      }
      const stored = storage.getItem<HITLCheckpoint>(STORAGE_KEYS.HITL_CHECKPOINT, true);
      if (!stored) return;
      // The checkpoint is stored under a single global key, so a checkpoint left
      // over from a PRIOR investigation must never be restored against a
      // different session — submitting it would POST a stale checkpoint_id /
      // session_id to the backend. Only restore when it belongs to the active
      // session; otherwise drop the stale key.
      const activeSid = storage.getItem(STORAGE_KEYS.SESSION_ID);
      if (stored.session_id && activeSid && stored.session_id !== activeSid) {
        storage.removeItem(STORAGE_KEYS.HITL_CHECKPOINT);
        return;
      }
      setHitlCheckpoint(stored);
    } catch (e) { dbg.warn("[Simulation] HITL checkpoint restore failed:", e); }
  }, []);

  const resetSimulation = useCallback(() => {
    activePhaseRef.current = "initial";
    expectingPipelineCompleteRef.current = false;
    hasFiredCompleteRef.current = false;
    setSessionId(null);
    setStatus("idle");
    setCompletedAgents([]);
    completedAgentsRef.current = [];
    setAgentUpdates({});
    setHitlCheckpoint(null);
    setIsDeepHITL(false);
    try { storage.removeItem(STORAGE_KEYS.HITL_CHECKPOINT); } catch (e) { dbg.warn("[Simulation] HITL checkpoint clear failed:", e); }
    try { storage.removeItem(STORAGE_KEYS.SESSION_ID); } catch { /* ignore */ }
    setErrorMessage(null);
    setPipelineMessage("");
    setPipelineThinking("");
    setArbiterStatus(null);
    setArbiterThinking(null);
    if (arbiterPollRef.current) {
      clearInterval(arbiterPollRef.current);
      arbiterPollRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const startSimulation = useCallback(() => {
    activePhaseRef.current = "initial";
    expectingPipelineCompleteRef.current = false;
    hasFiredCompleteRef.current = false;
    reconnectAttemptsRef.current = 0;
    setIsReconnecting(false);
    setStatus("initiating");
    setCompletedAgents([]);
    completedAgentsRef.current = [];
    setAgentUpdates({});
    setHitlCheckpoint(null);
    setIsDeepHITL(false);
    try { storage.removeItem(STORAGE_KEYS.HITL_CHECKPOINT); } catch (e) { dbg.warn("[Simulation] HITL checkpoint clear failed:", e); }
    setErrorMessage(null);
    setPipelineMessage("Preparing forensic agents...");
    setPipelineThinking("Preparing forensic agents...");
    setArbiterStatus(null);
    setArbiterThinking(null);
  }, []);

  // Dismiss HITL checkpoint
  const dismissCheckpoint = useCallback(() => {
    setHitlCheckpoint(null);
    try { storage.removeItem(STORAGE_KEYS.HITL_CHECKPOINT); } catch (e) { dbg.warn("[Simulation] HITL checkpoint clear failed:", e); }
  }, []);



const resumeInvestigation = useCallback(
    async (deep: boolean) => {
      const targetId = storage.getItem(STORAGE_KEYS.SESSION_ID);
      if (!targetId) {
        throw new SessionGoneError();
      }
      const { ensureAuthenticated } = await import("@/lib/api");
      await ensureAuthenticated();

      expectingPipelineCompleteRef.current = true;

      const { API_BASE, getMutationHeaders } = await import("@/lib/api");
      const headers = await getMutationHeaders({
        "Content-Type": "application/json",
      });
      const resultPhase = storage.getItem(`${STORAGE_KEYS.RESULT_PHASE}:${targetId}`);
      const expectedPhase = deep ? "initial" : resultPhase === "deep" ? "deep" : "initial";
      // Bound the resume request: without a timeout a briefly-unavailable
      // backend leaves the accept/deep flow on an infinite "synthesizing"
      // spinner with no recovery. On timeout the fetch throws and the caller's
      // catch surfaces a retryable error toast instead of hanging forever.
      const response = await fetch(
        `${API_BASE}/api/v1/sessions/${targetId}/resume`,
        {
          method: "POST",
          headers,
          credentials: "include",
          body: JSON.stringify({ deep_analysis: deep, expected_phase: expectedPhase }),
          signal: AbortSignal.timeout(30000),
        },
      );

      if (!response.ok) {
        expectingPipelineCompleteRef.current = false;
        let detail = `HTTP ${response.status}`;
        try {
          const body = (await response.json()) as { detail?: string };
          if (body.detail) detail = String(body.detail);
        } catch {
          /* ignore */
        }
        const err = new Error(detail);
        setErrorMessage("Failed to resume analysis");
        throw err;
      }

      setStatus(deep ? "analyzing" : "processing");
      setArbiterStatus(deep ? null : "synthesizing");
      setArbiterThinking(
        deep
          ? null
          : "Council Arbiter is synthesizing initial agent findings into the final report.",
      );
      if (deep) {
        playSoundRef.current?.("think");
        // Part 5.5 Fix: Abort any speculative frontend polling if we go DEEP
        const { arbiterControl } = await import("@/lib/arbiterControl");
        arbiterControl.abort();
      }

      if (arbiterPollRef.current) {
        clearInterval(arbiterPollRef.current);
        arbiterPollRef.current = null;
      }
      const startedAt = Date.now();
      // F-C-6: closure-local cancel flag so the in-flight async tick can't
      // dispatch setState on an unmounted/reset component after clearInterval.
      // Also checked against isMountedRef so navigation unmounts don't bleed.
      let cancelled = false;
      const guarded = (fn: () => void) => { if (!cancelled && isMountedRef.current) fn(); };
      arbiterPollRef.current = setInterval(async () => {
        if (cancelled || !isMountedRef.current) return;
        try {
          const st = await getArbiterStatus(targetId);
          if (cancelled || !isMountedRef.current) return;
          if (st.status === "complete") {
            cancelled = true;
            if (arbiterPollRef.current) {
              clearInterval(arbiterPollRef.current);
              arbiterPollRef.current = null;
            }
            expectingPipelineCompleteRef.current = false;
            guarded(() => setStatus((prev: SimulationStatus) => {
              if (prev !== "complete") {
                playSoundRef.current?.("complete");
                onCompleteRef.current?.();
              }
              return "complete";
            }));
          } else if (st.status === "error") {
            cancelled = true;
            if (arbiterPollRef.current) {
              clearInterval(arbiterPollRef.current);
              arbiterPollRef.current = null;
            }
            expectingPipelineCompleteRef.current = false;
            guarded(() => setErrorMessage(st.message || "Investigation failed"));
            guarded(() => setStatus("error"));
          } else if (Date.now() - startedAt > 300_000 && arbiterPollRef.current) {
            cancelled = true;
            clearInterval(arbiterPollRef.current);
            arbiterPollRef.current = null;
          }
        } catch {
          // WebSocket remains the primary path; polling is only a catch-up guard.
        }
      }, 3000);
    },
    [],
  );

  const clearPipelineThinking = useCallback(() => {
    setPipelineThinking("");
  }, []);

  const clearCompletedAgents = useCallback(() => {
    setCompletedAgents([]);
    completedAgentsRef.current = [];
    setAgentUpdates({});
    setIsDeepHITL(false);
    setPipelineMessage("Beginning deep analysis...");
    setPipelineThinking("");
    setStatus("analyzing");
    expectingPipelineCompleteRef.current = false;
  }, []);



  const restoreSimulationState = useCallback(
    (
      savedAgents: AgentUpdate[],
      restoredStatus: SimulationStatus = "awaiting_decision",
    ) => {
      setCompletedAgents(savedAgents);
      completedAgentsRef.current = [...savedAgents];
      setStatus(restoredStatus);
    },
    [],
  );

  // F-C-2: removed duplicate unmount cleanup. The single source of truth is
  // the unmount-only effect near `connectWebSocket` above (closes WS, clears
  // reconnect timer + arbiter poll). Keeping two cleanup effects made the
  // teardown order ambiguous in Strict Mode dev and could double-close.

  return {
    status,
    agentUpdates,
    completedAgents,
    pipelineMessage,
    pipelineThinking,
    arbiterStatus,
    arbiterThinking,
    startSimulation,
    connectWebSocket,
    resumeInvestigation,
    resetSimulation,
    dismissCheckpoint,
    clearCompletedAgents,
    clearPipelineThinking,
    restoreSimulationState,
    setSimulationPhase,
    hitlCheckpoint,
    isDeepHITL,
    errorMessage,
    revealQueue,
    revealPending,
    isReconnecting,
    streamStalled,
  };
};
