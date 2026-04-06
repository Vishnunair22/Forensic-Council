"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { AGENTS_DATA } from "@/lib/constants";

/** Dev-only logger — silenced in production builds */
const isDev = process.env.NODE_ENV !== "production";
const dbg = {
  log: isDev ? console.log.bind(console) : () => {},
  warn: isDev ? console.warn.bind(console) : () => {},
  error: isDev ? console.error.bind(console) : () => {},
};

import { createLiveSocket, BriefUpdate, HITLCheckpoint } from "@/lib/api";
import { SoundType } from "./useSound";
import type { AgentUpdate } from "@/components/evidence/AgentProgressDisplay";

// Backend uses "Agent1"–"Agent5"; frontend AGENTS_DATA uses "AGT-01"–"AGT-05".
// Normalize incoming agent IDs so all state keying is consistent.
const BACKEND_TO_FRONTEND_AGENT_ID: Record<string, string> = {
  Agent1: "AGT-01",
  Agent2: "AGT-02",
  Agent3: "AGT-03",
  Agent4: "AGT-04",
  Agent5: "AGT-05",
};
function normalizeAgentId(id: string | null | undefined): string | null {
  if (!id) return null;
  return BACKEND_TO_FRONTEND_AGENT_ID[id] ?? id;
}

type SimulationStatus =
  | "idle"
  | "analyzing"
  | "initiating"
  | "processing"
  | "awaiting_decision"
  | "complete"
  | "error";

type UseSimulationProps = {
  onAgentComplete?: (result: AgentUpdate) => void;
  onComplete?: () => void;
  playSound?: (type: SoundType) => void;
};

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
      }
    >
  >({});
  const [hitlCheckpoint, setHitlCheckpoint] = useState<HITLCheckpoint | null>(
    null,
  );
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [pipelineMessage, setPipelineMessage] = useState<string>("");
  const [pipelineThinking, setPipelineThinking] = useState<string>("");

  const wsRef = useRef<WebSocket | null>(null);
  const completedAgentsRef = useRef<AgentUpdate[]>([]);
  const [_sessionTimeout, _setSessionTimeout] = useState<Date | null>(null);
  /** True after POST /resume succeeds — PIPELINE_COMPLETE must not be dropped while still `awaiting_decision` from React's stale batch. */
  const expectingPipelineCompleteRef = useRef(false);

  // WebSocket reconnection config with exponential backoff
  const reconnectConfig = useRef({
    initialDelay: 1000,
    maxDelay: 30000,
    backoffFactor: 2,
    maxRetries: 12,
  });
  const reconnectAttemptsRef = useRef(0);

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
    (targetSessionId: string): Promise<void> => {
      // Store session ID so resumeInvestigation can use it directly
      setSessionId(targetSessionId);

      return new Promise((resolve, reject) => {
        // Disconnect existing
        if (wsRef.current) {
          wsRef.current.close();
          wsRef.current = null;
        }

        const messageQueue: BriefUpdate[] = [];
        let isProcessingQueue = false;
        let wsConnectionReady = false;

        const processQueue = async () => {
          if (isProcessingQueue || messageQueue.length === 0) return;
          isProcessingQueue = true;

          try {
            while (messageQueue.length > 0) {
              const update = messageQueue.shift();
              if (!update) break;

              dbg.log("[Simulation] Processing update from queue:", update);

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
                    };
                    const incomingId = normalizeAgentId(update.agent_id) ?? update.agent_id;

                    setAgentUpdates(
                      (
                        prev: Record<
                          string,
                          {
                            status: string;
                            thinking: string;
                            tools_done?: number;
                            tools_total?: number;
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
                      agent_id: normalizeAgentId(update.agent_id) ?? update.agent_id ?? "",
                      agent_name: update.agent_name || "",
                      brief_text: update.message,
                      decision_needed: "APPROVE, REDIRECT, or TERMINATE",
                      created_at: new Date().toISOString(),
                    };
                    setHitlCheckpoint(checkpoint);
                  }
                  break;

                case "AGENT_COMPLETE":
                  if (update.agent_id) {
                    const normalizedCompleteId = normalizeAgentId(update.agent_id) ?? update.agent_id;
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
                        tool_error_rate,
                        section_flags,
                        findings_preview,
                        tools_ran,
                        tools_skipped,
                        tools_failed,
                      } = update.data as Record<string, unknown>;
                      const parsedConfidence =
                        (typeof confidence === "number" ? confidence : null) ??
                        0.5;

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
                        error: typeof error === "string" ? error : null,
                        deep_analysis_pending:
                          typeof deep_analysis_pending === "boolean"
                            ? deep_analysis_pending
                            : undefined,
                        agent_verdict:
                          (typeof agent_verdict === "string"
                            ? (agent_verdict as AgentUpdate["agent_verdict"])
                            : null) ?? null,
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
                        completed_at: new Date().toISOString(),
                      };

                      // Upsert: later AGENT_COMPLETE for the same agent_id always wins
                      const existingIndex =
                        completedAgentsRef.current.findIndex(
                          (a: AgentUpdate) => a.agent_id === newUpdate.agent_id,
                        );
                      if (existingIndex >= 0) {
                        completedAgentsRef.current[existingIndex] = newUpdate;
                      } else {
                        completedAgentsRef.current.push(newUpdate);
                      }

                      const nextCompleted = [...completedAgentsRef.current];
                      setCompletedAgents(nextCompleted);
                      onAgentCompleteRef.current?.(newUpdate);

                      // Also transition to analyzing if still idle or initiating
                      setStatus((prev: SimulationStatus) =>
                        prev === "idle" || prev === "initiating" ? "analyzing" : prev,
                      );
                    }
                  }
                  break;

                case "PIPELINE_PAUSED":
                  setStatus("awaiting_decision");
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
              }
            }
          } finally {
            isProcessingQueue = false;
          }
        };

        const handleMessage = (event: MessageEvent) => {
          try {
            const update: BriefUpdate = JSON.parse(event.data);

            // Silently discard server-side keepalive pings — they carry no state.
            if ((update as { type: string }).type === "PING") return;

            dbg.log("[WebSocket] Received update, adding to queue:", update);

            const isCritical = ["PIPELINE_COMPLETE", "ERROR", "PIPELINE_PAUSED", "HITL_CHECKPOINT"].includes(update.type);
            if (isCritical) {
              messageQueue.unshift(update);
            } else {
              if (messageQueue.length >= 500) {
                let dropIdx = 0;
                while (dropIdx < messageQueue.length && ["PIPELINE_COMPLETE", "ERROR", "PIPELINE_PAUSED", "HITL_CHECKPOINT"].includes(messageQueue[dropIdx].type)) {
                  dropIdx++;
                }
                if (dropIdx < messageQueue.length) {
                  messageQueue.splice(dropIdx, 1);
                } else {
                  messageQueue.shift();
                }
                dbg.warn("[WebSocket] Queue limit reached, dropped oldest normal message");
              }
              messageQueue.push(update);
            }
            processQueue();
          } catch (error) {
            dbg.error("[WebSocket] Failed to parse message:", error);
          }
        };

        // Create socket and get the connection promise
        const { ws, connected } = createLiveSocket(targetSessionId);
        wsRef.current = ws;

        // Wire up message handler.
        // createLiveSocket attaches a bootstrap handler first (to resolve 'connected').
        // We wrap it so both handlers fire in sequence.
        // ws.onmessage has been changed in lib/api.ts to use addEventListener instead.
        // We can safely directly assign our simulation handler.
        ws.onmessage = handleMessage;

        // Handle close - reject if closed before/during connection, otherwise notify
        const handleClose = (event: CloseEvent) => {
          dbg.log("[WebSocket] Connection closed:", event.code, event.reason);
          wsRef.current = null;

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
                const delay = Math.min(
                  reconnectConfig.current.initialDelay *
                    Math.pow(reconnectConfig.current.backoffFactor, reconnectAttemptsRef.current),
                  reconnectConfig.current.maxDelay,
                );
                reconnectAttemptsRef.current++;
                setErrorMessage(
                  `Connection lost. Reconnecting in ${Math.round(delay / 1000)}s (attempt ${reconnectAttemptsRef.current}/${reconnectConfig.current.maxRetries})…`,
                );
                setTimeout(() => {
                  const currentSessionId = targetSessionId || sessionStorage.getItem("forensic_session_id");
                  if (currentSessionId) {
                    connectWebSocket(currentSessionId).catch(() => {
                      // Will be retried by next close event
                    });
                  }
                }, delay);
                return prev;
              } else {
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

        // Wait for connection - resolve or reject based on outcome
        connected
          .then(() => {
            wsConnectionReady = true;
            resolve();
          })
          .catch(() => {
            // connected promise settled (either onerror or onclose before open)
            if (!wsConnectionReady) {
              reject(new Error("WebSocket connection failed"));
            }
          });
      });
    },
    [],
  );

  // Cleanup WebSocket on unmount only.
  // IMPORTANT: This must NOT depend on sessionId — if it did, the cleanup would
  // fire every time connectWebSocket calls setSessionId(), killing the newly
  // created socket before it can connect (WebSocket closed before established).
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []);

  // Token expiry checker — reschedules when session changes, but does NOT
  // touch the WebSocket (that lives in the unmount-only effect above).
  useEffect(() => {
    let tokenExpiryTimeout: NodeJS.Timeout;
    const scheduleTokenExpiryCheck = () => {
      const expiryStr = sessionStorage.getItem("forensic_auth_token_expiry");
      if (!expiryStr) return;
      const expiry = parseInt(expiryStr);
      const now = Date.now();
      const timeToExpiry = expiry - now;
      const checkDelay = Math.max(0, timeToExpiry - 30000);

      tokenExpiryTimeout = setTimeout(() => {
        // Token expires soon — attempt refresh
        fetch("/api/v1/auth/refresh", {
          method: "POST",
          credentials: "include",
        })
          .then((response) => {
            if (!response.ok) {
              window.location.href = "/";
            } else {
              const currentSessionId = sessionId || sessionStorage.getItem("forensic_session_id");
              if (currentSessionId) {
                connectWebSocket(currentSessionId);
              }
              // Schedule next check
              scheduleTokenExpiryCheck();
            }
          })
          .catch(() => {
            window.location.href = "/";
          });
      }, checkDelay);
    };
    scheduleTokenExpiryCheck();

    return () => {
      clearTimeout(tokenExpiryTimeout);
    };
  }, [sessionId, connectWebSocket]);

  const resetSimulation = useCallback(() => {
    expectingPipelineCompleteRef.current = false;
    setSessionId(null);
    setStatus("idle");
    setCompletedAgents([]);
    completedAgentsRef.current = [];
    setAgentUpdates({});
    setHitlCheckpoint(null);
    setErrorMessage(null);
    setPipelineMessage("");
    setPipelineThinking("");

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  // Dismiss HITL checkpoint
  const dismissCheckpoint = useCallback(() => {
    setHitlCheckpoint(null);
  }, []);

  const resumeInvestigation = useCallback(
    async (deep: boolean) => {
      const targetId =
        sessionId || sessionStorage.getItem("forensic_session_id");
      if (!targetId) {
        throw new Error("No active session — cannot resume investigation.");
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
      if (deep) playSoundRef.current?.("think");
    },
    [sessionId],
  );

  const clearCompletedAgents = useCallback(() => {
    // Full reset for deep phase: clear both completed agents and running-state updates
    // so the initial-phase card contents don't persist into the deep phase.
    setCompletedAgents([]);
    completedAgentsRef.current = [];
    setAgentUpdates({});
    setPipelineMessage("");
    setPipelineThinking("");
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

  return {
    status,
    agentUpdates,
    completedAgents,
    pipelineMessage,
    pipelineThinking,
    startSimulation: resetSimulation,
    connectWebSocket,
    resumeInvestigation,
    resetSimulation,
    dismissCheckpoint,
    clearCompletedAgents,
    restoreSimulationState,
    hitlCheckpoint,
    errorMessage,
    totalAgents: AGENTS_DATA.length,
  };
};
