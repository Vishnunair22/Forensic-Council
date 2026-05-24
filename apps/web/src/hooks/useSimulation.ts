"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { flushSync } from "react-dom";
import { AGENTS as AGENTS_DATA } from "@/lib/constants";
import { storage, sessionOnlyStorage } from "@/lib/storage";
import { STORAGE_KEYS } from "@/lib/storageKeys";
import { clearInvestigationPersistence } from "@/lib/investigationStorage";

import { createLiveSocket, connectLiveSSE, BriefUpdate, HITLCheckpoint, getArbiterStatus, API_BASE, dbg } from "@/lib/api";
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
  const [_reconnectStatusMessage, setReconnectStatusMessage] = useState<string | null>(null);
  const [pipelineMessage, setPipelineMessage] = useState<string>("");
  const [pipelineThinking, setPipelineThinking] = useState<string>("");
  const [arbiterStatus, setArbiterStatus] = useState<string | null>(null);
  const [arbiterThinking, setArbiterThinking] = useState<string | null>(null);
  const activePhaseRef = useRef<SimulationPhase>("initial");

  const setSimulationPhase = useCallback((phase: SimulationPhase) => {
    activePhaseRef.current = phase;
  }, []);

  const wsRef = useRef<WebSocket | null>(null);
  const sseRef = useRef<{ close: () => void } | null>(null);
  const completedAgentsRef = useRef<AgentUpdate[]>([]);
  const lastSessionIdRef = useRef<string | null>(null);
  /** True after POST /resume succeeds — PIPELINE_COMPLETE must not be dropped while still `awaiting_decision` from React's stale batch. */
  const expectingPipelineCompleteRef = useRef(false);
  /** Tracks pending reconnect delay timer so it can be cancelled on unmount. */
  const reconnectTimerRef = useRef<NodeJS.Timeout | null>(null);

  // WebSocket reconnection config with exponential backoff
  const reconnectConfig = useRef({
    initialDelay: 1000,
    maxDelay: 30000,
    backoffFactor: 2,
    maxRetries: 12,
  });
  const reconnectAttemptsRef = useRef(0);
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
        setReconnectStatusMessage(null);
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
          if (messagePhase && messagePhase !== activePhaseRef.current) {
            dbg.log("[WebSocket] Ignoring stale phase message", {
              active: activePhaseRef.current,
              incoming: messagePhase,
              type: update.type,
            });
            return;
          }

          if (
            activePhaseRef.current === "deep" &&
            update.type === "PIPELINE_PAUSED" &&
            /initial analysis complete/i.test(update.message || "")
          ) {
            return;
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
                          thinking:
                            agentData.thinking ??
                            prev[incomingId]?.thinking ??
                            "",
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
                    const checkpoint: HITLCheckpoint = {
                      checkpoint_id: update.data.checkpoint_id as string,
                      session_id: update.session_id,
                      agent_id: update.agent_id ?? "",
                      agent_name: update.agent_name || "",
                      brief_text: update.message,
                      decision_needed: "APPROVE, REDIRECT, or TERMINATE",
                      created_at: new Date().toISOString(),
                    };
                    // Persist to storage so the modal survives a page refresh
                    try { storage.setItem(STORAGE_KEYS.HITL_CHECKPOINT, checkpoint, true); } catch { /* ignore */ }
                    setHitlCheckpoint(checkpoint);
                  }
                  break;

                case "HITL_EXPIRED":
                  setHitlCheckpoint(null);
                  try { storage.removeItem(STORAGE_KEYS.HITL_CHECKPOINT); } catch { /* ignore */ }
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
                      playSoundRef.current?.("agent");
                      onAgentCompleteRef.current?.(completedUpdate);

                      // Also transition to analyzing if still idle or initiating
                      setStatus((prev: SimulationStatus) =>
                        prev === "idle" || prev === "initiating" ? "analyzing" : prev,
                      );
                    }
                  }
                  break;

                case "PIPELINE_PAUSED":
                  setStatus("awaiting_decision");
                  setIsDeepHITL(
                    (update.data as Record<string, unknown> | undefined)
                      ?.status === "awaiting_deep_report",
                  );
                  playSoundRef.current?.("think");
                  break;

                case "PIPELINE_COMPLETE":
                  // Normally stay on awaiting_decision until the user chooses Accept / Deep.
                  // After resumeInvestigation(), React may still report awaiting_decision for one
                  // frame while the WS already carries PIPELINE_COMPLETE — honour the resume ref.
                  setStatus((prev: SimulationStatus) => {
                    if (
                      prev === "awaiting_decision" &&
                      !expectingPipelineCompleteRef.current
                    ) {
                      return prev;
                    }
                    expectingPipelineCompleteRef.current = false;
                    if (arbiterPollRef.current) {
                      clearInterval(arbiterPollRef.current);
                      arbiterPollRef.current = null;
                    }
                    if (prev !== "complete") {
                      playSoundRef.current?.("complete");
                      onCompleteRef.current?.();
                    }
                    return "complete";
                  });
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

              // Guard: flushSync throws a React invariant if called during an
              // active render or route transition (e.g. when router.push fires
              // mid-processing). Always fall back to a plain call so we never
              // crash the React tree to a blank page.
              try {
                flushSync(() => {
                  applyUpdate(update);
                });
              } catch (flushErr) {
                // Swallow the flushSync invariant violation and apply the
                // update without forced synchronous flushing. React will batch
                // it normally on the next commit.
                try { applyUpdate(update); } catch (applyErr) {
                  dbg.warn("[Simulation] applyUpdate fallback also failed:", applyErr);
                }
                dbg.warn("[Simulation] flushSync failed (likely during navigation), fell back to async apply:", flushErr);
              }
            }
          } finally {
            isProcessingQueue = false;
          }
        };

        const handleMessage = (event: MessageEvent) => {
          try {
            const update: BriefUpdate = JSON.parse(event.data);

            // Respond to server keepalive pings so the idle monitor stays reset.
            if ((update as { type: string }).type === "PING") {
              wsRef.current?.send(JSON.stringify({ type: "PONG", timestamp: Date.now() }));
              return;
            }

            dbg.log("[WebSocket] Received update, adding to queue:", update);

            const isCritical = [
              "PIPELINE_COMPLETE",
              "ERROR",
              "PIPELINE_PAUSED",
              "HITL_CHECKPOINT",
              "HITL_EXPIRED",
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
            if (isCritical) {
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
          const terminalCodes = [1011, 1013, 4001, 4003, 4004, 4010];
          if (terminalCodes.includes(event.code)) {
            dbg.warn("[WebSocket] Terminal close code received. Clearing session state.");
            setIsReconnecting(false);
            setReconnectStatusMessage(null);
            setSessionId(null);
            clearInvestigationPersistence();

            // If connection was already established, set to error state
            if (wsConnectionReady) {
              setErrorMessage(event.reason || "Investigation interrupted. Please restart.");
              setStatus("error");
            }
            // Reject the pending promise if it hasn't resolved
            if (!wsConnectionReady) {
              reject(new Error(event.reason || `Terminal Error (code ${event.code})`));
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
                setReconnectStatusMessage(
                  `Connection lost. Reconnecting in ${Math.round(delay / 1000)}s (attempt ${reconnectAttemptsRef.current}/${reconnectConfig.current.maxRetries})...`,
                );
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
                setReconnectStatusMessage(null);
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
        connected
          .then(async () => {
            wsConnectionReady = true;
            reconnectAttemptsRef.current = 0; // Reset backoff on successful connect
            setIsReconnecting(false);
            setReconnectStatusMessage(null);
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
                    setReconnectStatusMessage(sseErr.message);
                  }
                );
                sseRef.current = sseConnection;
                wsConnectionReady = true;
                setIsReconnecting(false);
                setReconnectStatusMessage(null);
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
        // Token expires soon — attempt refresh
        fetch(`${API_BASE}/api/v1/auth/refresh`, {
          method: "POST",
          credentials: "include",
        })
          .then((response) => {
            if (!response.ok) {
              sessionOnlyStorage.removeItem(STORAGE_KEYS.AUTH_TOKEN_EXPIRY);
              setErrorMessage("Session refresh failed. Re-authentication will be attempted on the next API request.");
              return;
            }

            const currentSessionId = sessionId || storage.getItem(STORAGE_KEYS.SESSION_ID);
            if (currentSessionId) {
              connectWebSocket(currentSessionId, true);
            }
            // Schedule next check
            scheduleTokenExpiryCheck();
          })
          .catch(() => {
            sessionOnlyStorage.removeItem(STORAGE_KEYS.AUTH_TOKEN_EXPIRY);
            setErrorMessage("Session refresh could not reach the backend. Keeping the current analysis view open.");
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
      const stored = storage.getItem<HITLCheckpoint>(STORAGE_KEYS.HITL_CHECKPOINT, true);
      if (stored) setHitlCheckpoint(stored);
    } catch { /* ignore */ }
  }, []);

  const resetSimulation = useCallback(() => {
    expectingPipelineCompleteRef.current = false;
    setSessionId(null);
    setStatus("idle");
    setCompletedAgents([]);
    completedAgentsRef.current = [];
    setAgentUpdates({});
    setHitlCheckpoint(null);
    setIsDeepHITL(false);
    try { storage.removeItem(STORAGE_KEYS.HITL_CHECKPOINT); } catch { /* ignore */ }
    try { storage.removeItem(STORAGE_KEYS.SESSION_ID); } catch { /* ignore */ }
    setErrorMessage(null);
    setReconnectStatusMessage(null);
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
    expectingPipelineCompleteRef.current = false;
    setStatus("initiating");
    setCompletedAgents([]);
    completedAgentsRef.current = [];
    setAgentUpdates({});
    setHitlCheckpoint(null);
    setIsDeepHITL(false);
    try { storage.removeItem(STORAGE_KEYS.HITL_CHECKPOINT); } catch { /* ignore */ }
    setErrorMessage(null);
    setReconnectStatusMessage(null);
    setPipelineMessage("Preparing forensic agents...");
    setPipelineThinking("Preparing forensic agents...");
    setArbiterStatus(null);
    setArbiterThinking(null);
  }, []);

  // Dismiss HITL checkpoint
  const dismissCheckpoint = useCallback(() => {
    setHitlCheckpoint(null);
    try { storage.removeItem(STORAGE_KEYS.HITL_CHECKPOINT); } catch { /* ignore */ }
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
      const response = await fetch(
        `${API_BASE}/api/v1/sessions/${targetId}/resume`,
        {
          method: "POST",
          headers,
          credentials: "include",
          body: JSON.stringify({ deep_analysis: deep }),
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
    revealQueue: [],
    revealPending: false,
    isReconnecting,
  };
};
