"use client";

import { useCallback } from "react";

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
                // Ascending chime — each call creates a slightly higher note
                // by anchoring to a cycle of 5 pentatonic pitches
                const PITCHES = [392, 440, 523.25, 587.33, 659.25]; // G4 A4 C5 D5 E5
                if (!(window as { __agentChimeIdx?: number }).__agentChimeIdx) {
                    (window as { __agentChimeIdx?: number }).__agentChimeIdx = 0;
                }
                const idx = ((window as { __agentChimeIdx?: number }).__agentChimeIdx ?? 0) % PITCHES.length;
                (window as { __agentChimeIdx?: number }).__agentChimeIdx = idx + 1;
                const freq = PITCHES[idx];

                osc.type = "sine";
                osc.frequency.setValueAtTime(freq, ctx.currentTime);
                osc.frequency.exponentialRampToValueAtTime(freq * 1.5, ctx.currentTime + 0.12);
                gain.gain.setValueAtTime(0.12, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.45);

                // Harmonic overtone for richness
                const osc2 = ctx.createOscillator();
                const gain2 = ctx.createGain();
                osc2.connect(gain2);
                gain2.connect(ctx.destination);
                osc2.type = "triangle";
                osc2.frequency.setValueAtTime(freq * 2, ctx.currentTime);
                gain2.gain.setValueAtTime(0.04, ctx.currentTime);
                gain2.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
                osc2.start(ctx.currentTime);
                osc2.stop(ctx.currentTime + 0.3);

                osc.start(ctx.currentTime);
                osc.stop(ctx.currentTime + 0.45);
            } else if (type === "think") {
                // Deep analysis start — descending sweep with a pulse feel
                osc.type = "sine";
                osc.frequency.setValueAtTime(660, ctx.currentTime);
                osc.frequency.exponentialRampToValueAtTime(330, ctx.currentTime + 0.4);
                gain.gain.setValueAtTime(0.08, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.5);
                osc.start(ctx.currentTime);
                osc.stop(ctx.currentTime + 0.5);

                // Soft echo pulse
                const osc2 = ctx.createOscillator();
                const gain2 = ctx.createGain();
                osc2.connect(gain2);
                gain2.connect(ctx.destination);
                osc2.type = "sine";
                osc2.frequency.setValueAtTime(330, ctx.currentTime + 0.25);
                osc2.frequency.exponentialRampToValueAtTime(220, ctx.currentTime + 0.55);
                gain2.gain.setValueAtTime(0, ctx.currentTime);
                gain2.gain.setValueAtTime(0.04, ctx.currentTime + 0.25);
                gain2.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.6);
                osc2.start(ctx.currentTime + 0.25);
                osc2.stop(ctx.currentTime + 0.6);
            } else if (type === "complete") {
                // Three-note ascending triumphant chord: C5 → E5 → G5
                const CHORD = [523.25, 659.25, 783.99];
                CHORD.forEach((freq, i) => {
                    const o = ctx.createOscillator();
                    const g = ctx.createGain();
                    o.connect(g);
                    g.connect(ctx.destination);
                    o.type = "sine";
                    const t = ctx.currentTime + i * 0.1;
                    o.frequency.setValueAtTime(freq, t);
                    o.frequency.exponentialRampToValueAtTime(freq * 1.02, t + 0.3);
                    g.gain.setValueAtTime(0, t);
                    g.gain.linearRampToValueAtTime(0.12, t + 0.05);
                    g.gain.exponentialRampToValueAtTime(0.001, t + 0.8);
                    o.start(t);
                    o.stop(t + 0.8);
                });
                // Silence the auto-created osc (not needed here)
                gain.gain.setValueAtTime(0, ctx.currentTime);
                osc.start(ctx.currentTime);
                osc.stop(ctx.currentTime + 0.01);
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
