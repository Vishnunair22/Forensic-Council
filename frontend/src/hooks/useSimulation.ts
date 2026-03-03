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

                                if (update.agent_id) {
                                    setActiveAgents((prev: Record<string, { status: string; thinking: string }>) => ({
                                        ...prev,
                                        [update.agent_id!]: {
                                            status: agentData.status || "running",
                                            thinking: agentData.thinking || "Analyzing..."
                                        }
                                    }));
                                }

                                if (agentData.status === "deliberating") {
                                    setStatus("processing"); // We'll detect 'deliberating' in the UI via thinking phrase or agent_id
                                } else {
                                    setStatus("processing");
                                }

                                // Play subtle 'think' sound to sync with text update
                                playSoundRef.current?.("think");
                            }
                            // Minimal delay just for React state flushing
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
                                    setActiveAgents((prev: Record<string, { status: string; thinking: string }>) => {
                                        const next = { ...prev };
                                        delete next[update.agent_id!];
                                        return next;
                                    });
                                    setCompletedAgents((prev: AgentResult[]) => [...prev, result]);
                                    onAgentCompleteRef.current?.(result);
                                    playSoundRef.current?.("agent");
                                }
                            }
                            // Minimal delay just for React state flushing
                            await new Promise(resolve => setTimeout(resolve, 50));
                            break;

                        case "PIPELINE_COMPLETE":
                            // Minimal delay for final agent render 
                            await new Promise(resolve => setTimeout(resolve, 50));
                            setStatus("complete");
                            onCompleteRef.current?.();
                            playSoundRef.current?.("complete");
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

            const handleMessage = (update: BriefUpdate) => {
                console.log("[WebSocket] Received update, adding to queue:", update);
                messageQueue.push(update);
                processQueue();
            };

            const handleClose = () => {
                console.log("[WebSocket] Connection closed");
                wsRef.current = null;
                setStatus((prev: SimulationStatus) => {
                    if (prev !== "complete" && prev !== "error" && prev !== "idle") {
                        setErrorMessage("Connection to server lost.");
                        return "error";
                    }
                    return prev;
                });
            };

            const ws = createLiveSocket(targetSessionId, handleMessage, handleClose);
            wsRef.current = ws;

            // Override onopen to resolve the promise
            const origOnOpen = ws.onopen;
            ws.onopen = (ev) => {
                if (origOnOpen && typeof origOnOpen === 'function') origOnOpen.call(ws, ev);
                setWsReady(true);
                resolve();
            };
            // Override onerror to reject the promise
            const origOnError = ws.onerror;
            ws.onerror = (ev) => {
                if (origOnError && typeof origOnError === 'function') origOnError.call(ws, ev);
                reject(new Error("WebSocket connection failed"));
            };
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
