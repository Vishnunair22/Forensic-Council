"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { AGENTS_DATA } from "@/lib/constants";
import { AgentResult } from "@/types";

/** Dev-only logger — silenced in production builds */
const isDev = process.env.NODE_ENV !== "production";
const dbg = {
    log: isDev ? console.log.bind(console) : () => {},
    warn: isDev ? console.warn.bind(console) : () => {},
    error: isDev ? console.error.bind(console) : () => {},
};

import { createLiveSocket, BriefUpdate, HITLCheckpoint } from "@/lib/api";
import { SoundType } from "./useSound";
import { AgentUpdate } from "@/components/evidence";

type SimulationStatus = "idle" | "analyzing" | "initiating" | "processing" | "awaiting_decision" | "complete" | "error";

type UseSimulationProps = {
    onAgentComplete?: (result: AgentResult) => void;
    onComplete?: () => void;
    playSound?: (type: SoundType) => void;
};

export const useSimulation = ({ onAgentComplete, onComplete, playSound }: UseSimulationProps) => {
    const [status, setStatus] = useState<SimulationStatus>("idle");
    const [completedAgents, setCompletedAgents] = useState<AgentUpdate[]>([]);
    const [agentUpdates, setAgentUpdates] = useState<Record<string, { status: string; thinking: string }>>({});
    const [hitlCheckpoint, setHitlCheckpoint] = useState<HITLCheckpoint | null>(null);
    const [sessionId, setSessionId] = useState<string | null>(null);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);

    const wsRef = useRef<WebSocket | null>(null);
    const completedAgentsRef = useRef<AgentUpdate[]>([]);
    // Phase generation: incremented on clearCompletedAgents so stale initial-phase
    // AGENT_COMPLETE messages arriving after deep mode starts are discarded.
    const phaseGenRef = useRef<number>(0);

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
    const connectWebSocket = useCallback((targetSessionId: string): Promise<void> => {
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
                            if (update.agent_id && update.data) {
                                const agentData = update.data as { status?: string; thinking?: string };
                                const incomingId = update.agent_id;

                                setAgentUpdates((prev: Record<string, { status: string; thinking: string }>) => ({
                                    ...prev,
                                    [incomingId]: {
                                        status: agentData.status || "running",
                                        thinking: agentData.thinking || "Analyzing...",
                                    }
                                }));
                                // Transition from initiating to analyzing on first real agent update
                                setStatus((prev: SimulationStatus) => prev === "initiating" ? "analyzing" : prev);
                            }
                            break;

                        case "HITL_CHECKPOINT":
                            if (update.data) {
                                const checkpoint: HITLCheckpoint = {
                                    checkpoint_id: update.data.checkpoint_id as string,
                                    session_id: update.session_id,
                                    agent_id: update.agent_id || "",
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
                                const agent = AGENTS_DATA.find(a => a.id === update.agent_id);
                                if (agent) {
                                    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- WebSocket message data is dynamic
                                    const { confidence, findings_count, error, deep_analysis_pending, status: agentStatus } = update.data as any;
                                    const parsedConfidence = confidence ?? agent.simulation.confidence / 100;

                                    // Capture phase gen at message-processing time to detect stale messages.
                                    // A stale initial-phase AGENT_COMPLETE should NOT overwrite a deep-phase result.
                                    const messagePhaseGen = (update as any)._phaseGen ?? 0;
                                    const isStaleInitialMessage = messagePhaseGen < phaseGenRef.current;

                                    const newUpdate: AgentUpdate = {
                                        agent_id: agent.id,
                                        agent_name: update.agent_name || agent.name,
                                        message: update.message || agent.simulation.result,
                                        status: agentStatus || "complete",
                                        confidence: parsedConfidence,
                                        findings_count: findings_count || 1,
                                        error: error,
                                        deep_analysis_pending: deep_analysis_pending,
                                    };

                                    // Completely discard stale initial-phase messages after deep mode starts
                                    if (!isStaleInitialMessage) {
                                        const existingIndex = completedAgentsRef.current.findIndex((a: AgentUpdate) => a.agent_id === newUpdate.agent_id);
                                        if (existingIndex >= 0) {
                                            completedAgentsRef.current[existingIndex] = newUpdate;
                                        } else {
                                            completedAgentsRef.current.push(newUpdate);
                                        }
                                    }

                                    const nextCompleted = [...completedAgentsRef.current];
                                    setCompletedAgents(nextCompleted);
                                    // Use type assertion since onAgentComplete is legacy, or just drop calling it if not needed.
                                    // But to be safe, we cast.
                                    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- AgentResult type mismatch in legacy callback
                                    onAgentCompleteRef.current?.(newUpdate as any);

                                    // Also transition to analyzing if still in initiating
                                    setStatus((prev: SimulationStatus) => prev === "initiating" ? "analyzing" : prev);
                                }
                            }
                            break;

                        case "PIPELINE_PAUSED":
                            setStatus("awaiting_decision");
                            playSoundRef.current?.("think");
                            break;

                        case "PIPELINE_COMPLETE":
                            // Status is ideally already set to "complete" when last agent finished
                            setStatus((prev: SimulationStatus) => {
                                if (prev !== "complete") {
                                    playSoundRef.current?.("complete");
                                    onCompleteRef.current?.();
                                    return "complete";
                                }
                                return prev;
                            });
                            break;

                        case "ERROR":
                            dbg.error("[WebSocket] Error:", update.message);
                            setErrorMessage(update.message || "Investigation failed");
                            setStatus("error");
                            break;
                    }
                }
                isProcessingQueue = false;
            };

            const handleMessage = (event: MessageEvent) => {
                try {
                    const update: BriefUpdate = JSON.parse(event.data);
                    dbg.log("[WebSocket] Received update, adding to queue:", update);
                    if (messageQueue.length >= 500) {
                        messageQueue.shift();
                        dbg.warn("[WebSocket] Queue limit reached, dropped oldest message");
                    }
                    // Tag the message with the current phase generation so stale
                    // initial-phase messages can be discarded after clearCompletedAgents().
                    (update as any)._phaseGen = phaseGenRef.current;
                    messageQueue.push(update);
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
            const bootstrapHandler = ws.onmessage;
            ws.onmessage = (event: MessageEvent) => {
                // Let the bootstrap handler run first (resolves connected promise)
                if (bootstrapHandler) bootstrapHandler.call(ws, event);
                // Then run our simulation handler
                handleMessage(event);
            };

            // Handle close - reject if closed before/during connection, otherwise notify
            const handleClose = (event: CloseEvent) => {
                dbg.log("[WebSocket] Connection closed:", event.code, event.reason);
                wsRef.current = null;

                // If connection was never established, reject the promise
                if (!wsConnectionReady) {
                    const reason = event.reason || `Connection failed (code ${event.code})`;
                    reject(new Error(reason));
                    return;
                }

                // Connection was established but closed - notify status
                setStatus((prev: SimulationStatus) => {
                    if (prev !== "complete" && prev !== "error" && prev !== "idle") {
                        setErrorMessage("Connection to server lost.");
                        return "error";
                    }
                    return prev;
                });
            };
            ws.onclose = handleClose;

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
    }, []);

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            if (wsRef.current) {
                wsRef.current.close();
                wsRef.current = null;
            }
        };
    }, []);

    const startSimulation = useCallback((newSessionId?: string) => {
        setCompletedAgents([]);
        completedAgentsRef.current = [];
        setAgentUpdates({});
        if (newSessionId) {
            setSessionId(newSessionId);
        }
        setStatus("initiating");
    }, []);

    const resetSimulation = useCallback(() => {
        setSessionId(null);
        setStatus("idle");
        setCompletedAgents([]);
        completedAgentsRef.current = [];
        setAgentUpdates({});
        setHitlCheckpoint(null);
        setErrorMessage(null);

        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }
    }, []);

    // Dismiss HITL checkpoint
    const dismissCheckpoint = useCallback(() => {
        setHitlCheckpoint(null);
    }, []);

    const resumeInvestigation = useCallback(async (deep: boolean) => {
        // Prefer hook state; fall back to sessionStorage set by evidence page
        const targetId = sessionId || sessionStorage.getItem("forensic_session_id");
        if (!targetId) return;
        try {
            const { ensureAuthenticated } = await import("@/lib/api");
            const token = await ensureAuthenticated();

            // Re-import API_BASE or just rely on relative path since we are in the browser
            // Actually, next.config.ts rewrites /api/v1/ to the backend. Just use relative path.
            const response = await fetch(`/api/v1/${targetId}/resume`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${token}`
                },
                body: JSON.stringify({ deep_analysis: deep })
            });
            if (!response.ok) throw new Error("Failed to resume investigation");

            setStatus(deep ? "analyzing" : "processing");
            if (deep) playSoundRef.current?.("think");
        } catch (error) {
            dbg.error("Error resuming investigation:", error);
            setErrorMessage("Failed to resume analysis");
        }
    }, [sessionId]);

    const clearCompletedAgents = useCallback(() => {
        // Increment phase generation so any in-flight AGENT_COMPLETE messages
        // from the initial pass are treated as stale and ignored.
        phaseGenRef.current += 1;
        setCompletedAgents([]);
        completedAgentsRef.current = [];
    }, []);

    return {
        status,
        agentUpdates,
        completedAgents,
        startSimulation,
        connectWebSocket,
        resumeInvestigation,
        resetSimulation,
        dismissCheckpoint,
        clearCompletedAgents,
        hitlCheckpoint,
        errorMessage,
        totalAgents: AGENTS_DATA.length
    };
};
