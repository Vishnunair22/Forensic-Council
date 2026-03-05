"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { AGENTS_DATA } from "@/lib/constants";
import { AgentResult } from "@/types";
import { createLiveSocket, BriefUpdate, HITLCheckpoint } from "@/lib/api";
import { SoundType } from "./useSound";

type SimulationStatus = "idle" | "analyzing" | "initiating" | "processing" | "complete" | "error";

type UseSimulationProps = {
    onAgentComplete?: (result: AgentResult) => void;
    onComplete?: () => void;
    playSound?: (type: SoundType) => void;
};

export const useSimulation = ({ onAgentComplete, onComplete, playSound }: UseSimulationProps) => {
    const [status, setStatus] = useState<SimulationStatus>("idle");
    const [completedAgents, setCompletedAgents] = useState<AgentResult[]>([]);
    const [activeAgents, setActiveAgents] = useState<Record<string, { status: string; thinking: string }>>({});
    const [hitlCheckpoint, setHitlCheckpoint] = useState<HITLCheckpoint | null>(null);
    const [sessionId, setSessionId] = useState<string | null>(null);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);
    const [wsReady, setWsReady] = useState(false);

    const wsRef = useRef<WebSocket | null>(null);
    const thinkingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const completedAgentsRef = useRef<AgentResult[]>([]);

    // Sequential Activation Queue
    const pendingActivationsRef = useRef<Array<{ agent_id: string; thinking: string }>>([]);
    const currentlyActiveRef = useRef<string | null>(null);

    useEffect(() => {
        completedAgentsRef.current = completedAgents;
    }, [completedAgents]);

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

    // Cycle thinking phrases for the currently active agent to keep UI alive
    const activeAgentIds = Object.keys(activeAgents).sort().join(",");

    useEffect(() => {
        const activeIds = Object.keys(activeAgents);
        if (activeIds.length === 0) return;

        const activeId = activeIds[0]; // always one at a time now
        const agentDef = AGENTS_DATA.find(a => a.id === activeId);
        if (!agentDef || agentDef.simulation.thinkingPhrases.length === 0) return;

        let phraseIndex = 0;
        const interval = setInterval(() => {
            phraseIndex = (phraseIndex + 1) % agentDef.simulation.thinkingPhrases.length;
            setActiveAgents(prev => {
                if (!prev[activeId]) return prev;
                return {
                    ...prev,
                    [activeId]: {
                        ...prev[activeId],
                        thinking: agentDef.simulation.thinkingPhrases[phraseIndex],
                    }
                };
            });
        }, 2000);

        return () => clearInterval(interval);
    }, [activeAgentIds]);

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

            const activateNextPending = () => {
                if (pendingActivationsRef.current.length === 0) {
                    currentlyActiveRef.current = null;
                    return;
                }
                const next = pendingActivationsRef.current.shift()!;
                currentlyActiveRef.current = next.agent_id;
                setActiveAgents({
                    [next.agent_id]: { status: "running", thinking: next.thinking }
                });
                setStatus("analyzing");
            };

            const processQueue = async () => {
                if (isProcessingQueue || messageQueue.length === 0) return;
                isProcessingQueue = true;

                while (messageQueue.length > 0) {
                    const update = messageQueue.shift();
                    if (!update) break;

                    console.log("[Simulation] Processing update from queue:", update);

                    switch (update.type) {
                        case "AGENT_UPDATE":
                            if (update.agent_id && update.data) {
                                const agentData = update.data as { status?: string; thinking?: string };
                                const incomingId = update.agent_id;

                                if (
                                    currentlyActiveRef.current === null &&
                                    pendingActivationsRef.current.length === 0
                                ) {
                                    // Nothing active — activate immediately
                                    currentlyActiveRef.current = incomingId;
                                    setActiveAgents({
                                        [incomingId]: {
                                            status: agentData.status || "running",
                                            thinking: agentData.thinking || "Analyzing...",
                                        }
                                    });
                                    setStatus("analyzing");
                                    // Play sound when ANY new agent becomes active natively
                                    playSoundRef.current?.("think");
                                } else if (currentlyActiveRef.current === incomingId) {
                                    // Update thinking text for the currently active agent only
                                    setActiveAgents(prev => ({
                                        ...prev,
                                        [incomingId]: {
                                            status: agentData.status || "running",
                                            thinking: agentData.thinking || prev[incomingId]?.thinking || "Analyzing...",
                                        }
                                    }));
                                } else if (!pendingActivationsRef.current.find(p => p.agent_id === incomingId)) {
                                    // Queue it — don't activate yet
                                    pendingActivationsRef.current.push({
                                        agent_id: incomingId,
                                        thinking: agentData.thinking || "Analyzing...",
                                    });
                                }
                            }
                            await new Promise(resolve => setTimeout(resolve, 50));
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
                                        thinking: update.message,
                                    };

                                    const nextCompleted = [...completedAgentsRef.current, result];
                                    setCompletedAgents(nextCompleted);
                                    onAgentCompleteRef.current?.(result);
                                    // Play sound when individual agent finishes
                                    playSoundRef.current?.("agent");

                                    // Clear this agent from active
                                    setActiveAgents(prev => {
                                        const next = { ...prev };
                                        delete next[update.agent_id!];
                                        return next;
                                    });

                                    // Reset current tracking and drain queue
                                    currentlyActiveRef.current = null;
                                    activateNextPending();

                                    // Check if all expected agents are done (sequential or fast parallel)
                                    const totalExpected = AGENTS_DATA.length; // All 5 specialist agents (Arbiter is not in AGENTS_DATA)
                                    if (nextCompleted.length >= totalExpected) {
                                        setStatus("complete");
                                        onCompleteRef.current?.();
                                        playSoundRef.current?.("complete");
                                    }
                                }
                            }
                            await new Promise(resolve => setTimeout(resolve, 50));
                            break;

                        case "PIPELINE_COMPLETE":
                            // Status is ideally already set to "complete" when last agent finished
                            setStatus(prev => {
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
                    messageQueue.push(update);
                    processQueue();
                } catch (error) {
                    console.error("[WebSocket] Failed to parse message:", error);
                }
            };

            // Create socket and get the connection promise
            const { ws, connected } = createLiveSocket(targetSessionId);
            wsRef.current = ws;

            // Wire up message handler
            ws.onmessage = handleMessage;

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
            if (thinkingIntervalRef.current) {
                clearInterval(thinkingIntervalRef.current);
                thinkingIntervalRef.current = null;
            }
        };
    }, []);

    const startSimulation = useCallback((newSessionId?: string) => {
        setCompletedAgents([]);
        setActiveAgents({});
        setWsReady(false);
        if (newSessionId) {
            setSessionId(newSessionId);
            setStatus("initiating");
        }
    }, []);

    const resetSimulation = useCallback(() => {
        setSessionId(null);
        setStatus("idle");
        setCompletedAgents([]);
        setActiveAgents({});
        setHitlCheckpoint(null);
        setErrorMessage(null);
        setWsReady(false);

        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }
        if (thinkingIntervalRef.current) {
            clearInterval(thinkingIntervalRef.current);
            thinkingIntervalRef.current = null;
        }
    }, []);

    // Dismiss HITL checkpoint
    const dismissCheckpoint = useCallback(() => {
        setHitlCheckpoint(null);
    }, []);

    return {
        status,
        activeAgents,
        completedAgents,
        startSimulation,
        connectWebSocket,
        resetSimulation,
        dismissCheckpoint,
        hitlCheckpoint,
        errorMessage,
        totalAgents: AGENTS_DATA.length
    };
};
