"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { AGENTS_DATA } from "@/lib/constants";
import { AgentResult } from "@/types";
import { createLiveSocket, BriefUpdate, HITLCheckpoint } from "@/lib/api";
import { SoundType } from "./useSound";

type SimulationStatus = "idle" | "analyzing" | "initiating" | "processing" | "awaiting_decision" | "complete" | "error";

type UseSimulationProps = {
    onAgentComplete?: (result: AgentResult) => void;
    onComplete?: () => void;
    playSound?: (type: SoundType) => void;
};

export const useSimulation = ({ onAgentComplete, onComplete, playSound }: UseSimulationProps) => {
    const [status, setStatus] = useState<SimulationStatus>("idle");
    const [completedAgents, setCompletedAgents] = useState<AgentResult[]>([]);
    const [agentUpdates, setAgentUpdates] = useState<Record<string, { status: string; thinking: string }>>({});
    const [hitlCheckpoint, setHitlCheckpoint] = useState<HITLCheckpoint | null>(null);
    const [sessionId, setSessionId] = useState<string | null>(null);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);
    const [wsReady, setWsReady] = useState(false);

    // UI Sequence Tracking (0 to 4)
    const [uiSequenceIndex, setUiSequenceIndex] = useState(0);

    const wsRef = useRef<WebSocket | null>(null);
    const completedAgentsRef = useRef<AgentResult[]>([]);

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

    // Sequence progression effect
    useEffect(() => {
        if (status !== "analyzing" && status !== "processing" && status !== "initiating") return;

        // If we've processed all agents in the UI
        if (uiSequenceIndex >= AGENTS_DATA.length) {
            if (completedAgentsRef.current.length >= AGENTS_DATA.length) {
                setStatus("complete");
                onCompleteRef.current?.();
                playSoundRef.current?.("complete");
            }
            return;
        }

        const currentAgent = AGENTS_DATA[uiSequenceIndex];
        if (!currentAgent) return;

        // Has the currently displayed agent actually completed in the background?
        const isCompleted = completedAgentsRef.current.find((a: AgentResult) => a.id === currentAgent.id);

        if (isCompleted) {
            // It has completed. Wait 1s then advance the UI to the next agent.
            const timer = setTimeout(() => {
                setUiSequenceIndex((prev: number) => {
                    const next = prev + 1;
                    if (next < AGENTS_DATA.length) {
                        playSoundRef.current?.("think");
                    }
                    return next;
                });
            }, 1000);
            return () => clearTimeout(timer);
        }
    }, [uiSequenceIndex, completedAgents.length, status]);

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

                    console.log("[Simulation] Processing update from queue:", update);

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
                                    const confidence = (update.data as { confidence?: number })?.confidence ?? agent.simulation.confidence / 100;
                                    const result: AgentResult = {
                                        id: agent.id,
                                        name: agent.name,
                                        role: agent.role,
                                        result: update.message || agent.simulation.result,
                                        confidence,
                                        thinking: undefined,
                                    };

                                    if (!completedAgentsRef.current.find((a: AgentResult) => a.id === result.id)) {
                                        completedAgentsRef.current.push(result);
                                    }
                                    const nextCompleted = [...completedAgentsRef.current];
                                    setCompletedAgents(nextCompleted);
                                    onAgentCompleteRef.current?.(result);
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
                            console.error("[WebSocket] Error:", update.message);
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
                    console.log("[WebSocket] Received update, adding to queue:", update);
                    if (messageQueue.length >= 500) {
                        messageQueue.shift();
                        console.warn("[WebSocket] Queue limit reached, dropped oldest message");
                    }
                    messageQueue.push(update);
                    processQueue();
                } catch (error) {
                    console.error("[WebSocket] Failed to parse message:", error);
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
                console.log("[WebSocket] Connection closed:", event.code, event.reason);
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
                    setWsReady(true);
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
        setUiSequenceIndex(0);
        setWsReady(false);
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
        setUiSequenceIndex(0);
        setHitlCheckpoint(null);
        setErrorMessage(null);
        setWsReady(false);

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
        if (!sessionId) return;
        try {
            const token = sessionStorage.getItem('forensic_token') || localStorage.getItem('forensic_token');
            const response = await fetch(`/api/v1/investigation/${sessionId}/resume`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${token}`
                },
                body: JSON.stringify({ deep_analysis: deep })
            });
            if (!response.ok) throw new Error("Failed to resume investigation");

            setStatus(deep ? "analyzing" : "processing");
            if (deep) playSoundRef.current?.("process");
        } catch (error) {
            console.error("Error resuming investigation:", error);
            setErrorMessage("Failed to resume analysis");
        }
    }, [sessionId]);

    return {
        status,
        uiSequenceIndex,
        agentUpdates,
        completedAgents,
        startSimulation,
        connectWebSocket,
        resumeInvestigation,
        resetSimulation,
        dismissCheckpoint,
        hitlCheckpoint,
        errorMessage,
        totalAgents: AGENTS_DATA.length
    };
};
