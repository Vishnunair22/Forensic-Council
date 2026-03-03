"use client";

import { useCallback, useEffect, useRef } from "react";

export type SoundType = "success" | "error" | "agent" | "complete" | "think" | "click" | "upload";

let globalCtx: AudioContext | null = null;

type AudioContextConstructor = new () => AudioContext;

export function useSound() {
    const playSound = useCallback((type: SoundType) => {
        try {
            if (typeof window === "undefined") return;

            if (!globalCtx) {
                const AC = window.AudioContext || (window as unknown as { webkitAudioContext: AudioContextConstructor }).webkitAudioContext;
                if (AC) {
                    globalCtx = new AC();
                }
            }

            const ctx = globalCtx;
            if (!ctx) return;

            // Resume if suspended (browser auto-play policy)
            if (ctx.state === 'suspended') {
                ctx.resume().catch(console.error);
            }

            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);

            if (type === "success" || type === "upload") {
                osc.type = "sine";
                osc.frequency.setValueAtTime(523.25, ctx.currentTime);
                osc.frequency.exponentialRampToValueAtTime(1046.5, ctx.currentTime + 0.1);
                gain.gain.setValueAtTime(0.1, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);
                osc.start(ctx.currentTime);
                osc.stop(ctx.currentTime + 0.3);
            } else if (type === "click") {
                osc.type = "sine";
                osc.frequency.setValueAtTime(600, ctx.currentTime);
                osc.frequency.exponentialRampToValueAtTime(300, ctx.currentTime + 0.1);
                gain.gain.setValueAtTime(0.05, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.1);
                osc.start(ctx.currentTime);
                osc.stop(ctx.currentTime + 0.1);
            } else if (type === "agent") {
                osc.type = "triangle";
                osc.frequency.setValueAtTime(440, ctx.currentTime); // A4
                gain.gain.setValueAtTime(0.05, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.1);
                osc.start(ctx.currentTime);
                osc.stop(ctx.currentTime + 0.1);
            } else if (type === "think") {
                // Subtle low blip for thinking start
                osc.type = "sine";
                osc.frequency.setValueAtTime(220, ctx.currentTime);
                gain.gain.setValueAtTime(0.02, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.05);
                osc.start(ctx.currentTime);
                osc.stop(ctx.currentTime + 0.05);
            } else if (type === "complete") {
                osc.type = "sine";
                osc.frequency.setValueAtTime(440, ctx.currentTime);
                osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.2);
                gain.gain.setValueAtTime(0.1, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.5);
                osc.start(ctx.currentTime);
                osc.stop(ctx.currentTime + 0.5);
            } else if (type === "error") {
                osc.type = "sawtooth";
                osc.frequency.setValueAtTime(200, ctx.currentTime);
                osc.frequency.exponentialRampToValueAtTime(150, ctx.currentTime + 0.2);
                gain.gain.setValueAtTime(0.1, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);

                // Add a second low beep for emphasis
                const osc2 = ctx.createOscillator();
                const gain2 = ctx.createGain();
                osc2.connect(gain2);
                gain2.connect(ctx.destination);
                osc2.type = "sawtooth";
                osc2.frequency.setValueAtTime(150, ctx.currentTime + 0.15);
                osc2.frequency.exponentialRampToValueAtTime(100, ctx.currentTime + 0.35);
                gain2.gain.setValueAtTime(0, ctx.currentTime);
                gain2.gain.setValueAtTime(0.1, ctx.currentTime + 0.15);
                gain2.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.45);

                osc.start(ctx.currentTime);
                osc.stop(ctx.currentTime + 0.3);
                osc2.start(ctx.currentTime + 0.15);
                osc2.stop(ctx.currentTime + 0.45);
            }
        } catch (e) {
            console.warn("Audio Context Error", e);
        }
    }, []);

    return { playSound };
}
