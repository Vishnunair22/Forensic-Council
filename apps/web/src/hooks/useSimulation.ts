"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { AGENTS as AGENTS_DATA } from "@/lib/constants";
import { storage } from "@/lib/storage";

const HITL_CHECKPOINT_KEY = "forensic_hitl_checkpoint";
const SESSION_ID_KEY = "forensic_session_id";
const AUTH_TOKEN_EXPIRY_KEY = "forensic_auth_token_expiry";

/** Dev-only logger — silenced in production builds */
const isDev = process.env.NODE_ENV !== "production";
const dbg = {
  log: isDev ? console.log.bind(console) : () => {},
  warn: isDev ? console.warn.bind(console) : () => {},
  error: isDev ? console.error.bind(console) : () => {},
};

import { createLiveSocket, BriefUpdate, HITLCheckpoint, getArbiterStatus } from "@/lib/api";
import { SoundType } from "./useSound";
import type { AgentUpdate } from "@/components/evidence/AgentProgressDisplay";

// Backend and Frontend share unified Agent IDs "Agent1"–"Agent5".

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
  const [revealQueue, setRevealQueue] = useState<AgentUpdate[]>([]);
  const isRevealingRef = useRef(false);

  const wsRef = useRef<WebSocket | null>(null);
  const completedAgentsRef = useRef<AgentUpdate[]>([]);
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
                      agent_id: update.agent_id ?? "",
                      agent_name: update.agent_name || "",
                      brief_text: update.message,
                      decision_needed: "APPROVE, REDIRECT, or TERMINATE",
                      created_at: new Date().toISOString(),
                    };
                    // Persist to storage so the modal survives a page refresh
                    try { storage.setItem(HITL_CHECKPOINT_KEY, checkpoint, true); } catch { /* ignore */ }
                    setHitlCheckpoint(checkpoint);
                  }
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
                        tool_error_rate,
                        section_flags,
                        findings_preview,
                        tools_ran,
                        tools_skipped,
                        tools_failed,
                        degraded,
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
                        error: typeof error === "string" ? error : undefined,
                        deep_analysis_pending:
                          typeof deep_analysis_pending === "boolean"
                            ? deep_analysis_pending
                            : undefined,
                        agent_verdict:
                          typeof agent_verdict === "string"
                            ? (agent_verdict as AgentUpdate["agent_verdict"])
                            : undefined,
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
                        completed_at: new Date().toISOString(),
                      };

                      // Upsert: for deep-phase completions, MERGE with the
                      // initial-phase data instead of replacing it. This preserves
                      // the initial findings_preview and section_flags while
                      // appending deep-specific fields.
                      const existingIndex =
                        completedAgentsRef.current.findIndex(
                          (a: AgentUpdate) => a.agent_id === newUpdate.agent_id,
                        );
                      if (existingIndex >= 0) {
                        const existing = completedAgentsRef.current[existingIndex];
                        const mergedUpdate: AgentUpdate = {
                          ...newUpdate,
                          // Keep initial message if deep message is generic
                          message: newUpdate.message || existing.message,
                          // Merge findings previews: initial first, then deep
                          findings_preview: [
                            ...(existing.findings_preview || []),
                            ...(newUpdate.findings_preview || []),
                          ],
                          // Merge section_flags: initial first, then deep (dedup by id)
                          section_flags: [
                            ...(existing.section_flags || []),
                            ...(newUpdate.section_flags || []).filter(
                              (ns) => !(existing.section_flags || []).some(
                                (es) => ns.id && es.id && ns.id === es.id
                              )
                            ),
                          ],
                          // Sum findings counts from both phases
                          findings_count: (existing.findings_count || 0) + (newUpdate.findings_count || 0),
                          // Use the lower (worse) confidence
                          confidence: Math.min(existing.confidence || 1, newUpdate.confidence || 1),
                          // Deep-phase verdict takes precedence if present
                          agent_verdict: newUpdate.agent_verdict || existing.agent_verdict,
                        };
                        completedAgentsRef.current[existingIndex] = mergedUpdate;
                      } else {
                        completedAgentsRef.current.push(newUpdate);
                      }

                      const nextToQueue = existingIndex >= 0 ? completedAgentsRef.current[existingIndex] : newUpdate;
                      setRevealQueue((prev) => [...prev, nextToQueue]);

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
            // Proactive trim: keep queue under limit BEFORE pushing so
            // high-throughput bursts cannot accumulate thousands of items.
            const MAX_QUEUE = 500;
            while (messageQueue.length >= MAX_QUEUE) {
              const dropIdx = messageQueue.findIndex(
                (m) => !["PIPELINE_COMPLETE", "ERROR", "PIPELINE_PAUSED", "HITL_CHECKPOINT"].includes(m.type),
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
        wsRef.current = ws;

        // Wire up message handler.
        // createLiveSocket attaches a bootstrap listener via addEventListener (to resolve 'connected').
        // Use addEventListener here too so both handlers fire independently and neither overwrites the other.
        ws.addEventListener("message", handleMessage);

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
                  const currentSessionId = targetSessionId || storage.getItem<string>(SESSION_ID_KEY);
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

        // Wait for connection - resolve or reject based on outcome.
        // On success (including reconnects) rehydrate state from the arbiter status
        // endpoint so missed WS messages during the gap don't leave the UI stale.
        connected
          .then(async () => {
            wsConnectionReady = true;
            resolve();
            // Rehydrate: if the arbiter reached a terminal state while the socket
            // was down, catch up immediately. The arbiter-status endpoint returns
            // "complete" | "error" | "running" | "not_found" — never "awaiting_decision"
            // (that transition is WS-only via PIPELINE_PAUSED and is implicitly
            // restored by the HITL checkpoint sessionStorage key above).
            try {
              const currentSid = targetSessionId || storage.getItem<string>(SESSION_ID_KEY);
              if (currentSid) {
                const st = await getArbiterStatus(currentSid);
                if (st.status === "complete") {
                  expectingPipelineCompleteRef.current = true;
                  setStatus("complete");
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
      const expiryStr = storage.getItem<string>(AUTH_TOKEN_EXPIRY_KEY);
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
              const currentSessionId = sessionId || storage.getItem<string>(SESSION_ID_KEY);
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

  // Restore any pending HITL checkpoint that survived a page refresh
  useEffect(() => {
    try {
      const stored = storage.getItem<HITLCheckpoint>(HITL_CHECKPOINT_KEY, true);
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
    try { storage.removeItem(HITL_CHECKPOINT_KEY); } catch { /* ignore */ }
    try { storage.removeItem(SESSION_ID_KEY); } catch { /* ignore */ }
    setErrorMessage(null);
    setPipelineThinking("");
    setRevealQueue([]);
    isRevealingRef.current = false;

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  // Dismiss HITL checkpoint
  const dismissCheckpoint = useCallback(() => {
    setHitlCheckpoint(null);
    try { storage.removeItem(HITL_CHECKPOINT_KEY); } catch { /* ignore */ }
  }, []);

  const resumeInvestigation = useCallback(
    async (deep: boolean) => {
      const targetId =
        sessionId || storage.getItem<string>(SESSION_ID_KEY);
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
    setPipelineMessage("");
    setPipelineThinking("");
    setRevealQueue([]);
    isRevealingRef.current = false;
  }, []);

  // --- Sequential Reveal Pacing Effect ---
  useEffect(() => {
    if (revealQueue.length === 0 || isRevealingRef.current) return;

    isRevealingRef.current = true;
    
    const processNext = () => {
      setRevealQueue((prev) => {
        if (prev.length === 0) {
          isRevealingRef.current = false;
          return prev;
        }

        const [next, ...rest] = prev;
        
        // Add to completed list
        setCompletedAgents((current) => {
          const exists = current.some(a => a.agent_id === next.agent_id);
          if (exists) {
            return current.map(a => a.agent_id === next.agent_id ? next : a);
          }
          return [...current, next];
        });
        
        // Trigger Sound & Callback
        playSoundRef.current?.("agent");
        onAgentCompleteRef.current?.(next);

        if (rest.length > 0) {
          setTimeout(processNext, 3000); // 3s delay
        } else {
          isRevealingRef.current = false;
        }
        
        return rest;
      });
    };

    processNext();
  }, [revealQueue.length]);

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
