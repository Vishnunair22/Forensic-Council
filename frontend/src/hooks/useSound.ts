"use client";

import { useCallback } from "react";

export type SoundType = "success" | "error" | "agent" | "complete" | "think" | "click" | "upload";

let globalCtx: AudioContext | null = null;

type AudioContextConstructor = new () => AudioContext;

/** Tiny helper: create a soft reverb-like tail using a convolver with impulse noise */
function createSoftGain(ctx: AudioContext, peakGain: number, attackTime: number, releaseTime: number): GainNode {
    const g = ctx.createGain();
    g.gain.setValueAtTime(0, ctx.currentTime);
    g.gain.linearRampToValueAtTime(peakGain, ctx.currentTime + attackTime);
    g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + attackTime + releaseTime);
    return g;
}

export function useSound() {
    const playSound = useCallback((type: SoundType) => {
        try {
            if (typeof window === "undefined") return;

            if (!globalCtx) {
                const AC = window.AudioContext || (window as unknown as { webkitAudioContext: AudioContextConstructor }).webkitAudioContext;
                if (AC) globalCtx = new AC();
            }

            const ctx = globalCtx;
            if (!ctx) return;

            if (ctx.state === "suspended") ctx.resume().catch(() => {});

            const t = ctx.currentTime;

            // ── Master output limiter to prevent clipping ──────────────────
            const limiter = ctx.createDynamicsCompressor();
            limiter.threshold.value = -6;
            limiter.knee.value = 6;
            limiter.ratio.value = 10;
            limiter.attack.value = 0.003;
            limiter.release.value = 0.1;
            limiter.connect(ctx.destination);

            const out = limiter;

            if (type === "click") {
                // Ultra-subtle: single sine tick at 880 Hz, 60 ms, very soft
                const o = ctx.createOscillator();
                const g = ctx.createGain();
                o.type = "sine";
                o.frequency.value = 880;
                g.gain.setValueAtTime(0, t);
                g.gain.linearRampToValueAtTime(0.028, t + 0.005);
                g.gain.exponentialRampToValueAtTime(0.0001, t + 0.06);
                o.connect(g); g.connect(out);
                o.start(t); o.stop(t + 0.07);

            } else if (type === "upload" || type === "success") {
                // Warm two-note rise: 440 → 660 Hz, soft sine, 280 ms
                const freqs = [440, 660];
                freqs.forEach((freq, i) => {
                    const delay = i * 0.09;
                    const o = ctx.createOscillator();
                    const g = createSoftGain(ctx, 0.038, 0.012, 0.22);
                    o.type = "sine";
                    o.frequency.value = freq;
                    o.connect(g); g.connect(out);
                    o.start(t + delay); o.stop(t + delay + 0.28);
                });

            } else if (type === "agent") {
                // Soft water-drop chime: single pentatonic note, triangle wave, 400 ms fade
                const PITCHES = [349.23, 392, 440, 493.88, 523.25]; // F4 G4 A4 B4 C5
                const idx = ((window as { __agentChimeIdx?: number }).__agentChimeIdx ?? 0) % PITCHES.length;
                (window as { __agentChimeIdx?: number }).__agentChimeIdx = idx + 1;
                const freq = PITCHES[idx];

                const o = ctx.createOscillator();
                const g = createSoftGain(ctx, 0.042, 0.008, 0.38);
                o.type = "triangle";
                o.frequency.setValueAtTime(freq * 1.02, t);
                o.frequency.exponentialRampToValueAtTime(freq, t + 0.04);
                o.connect(g); g.connect(out);
                o.start(t); o.stop(t + 0.42);

            } else if (type === "think") {
                // Deep breath-in feel: low sine swell 200→280 Hz, 600 ms, very soft
                const o = ctx.createOscillator();
                const g = ctx.createGain();
                o.type = "sine";
                o.frequency.setValueAtTime(200, t);
                o.frequency.linearRampToValueAtTime(280, t + 0.3);
                o.frequency.linearRampToValueAtTime(240, t + 0.6);
                g.gain.setValueAtTime(0, t);
                g.gain.linearRampToValueAtTime(0.032, t + 0.15);
                g.gain.exponentialRampToValueAtTime(0.0001, t + 0.65);
                o.connect(g); g.connect(out);
                o.start(t); o.stop(t + 0.68);

            } else if (type === "complete") {
                // Soft three-note crystalline chime: C5 E5 G5, triangle, staggered 120 ms
                const CHORD = [523.25, 659.25, 783.99];
                CHORD.forEach((freq, i) => {
                    const delay = i * 0.12;
                    const o = ctx.createOscillator();
                    const g = ctx.createGain();
                    o.type = "triangle";
                    o.frequency.value = freq;
                    g.gain.setValueAtTime(0, t + delay);
                    g.gain.linearRampToValueAtTime(0.045, t + delay + 0.01);
                    g.gain.exponentialRampToValueAtTime(0.0001, t + delay + 0.75);
                    o.connect(g); g.connect(out);
                    o.start(t + delay); o.stop(t + delay + 0.78);
                });

            } else if (type === "error") {
                // Gentle dissonance: two slightly detuned sines, very low volume, 400 ms
                const pairs = [{ f: 320, v: 0.03 }, { f: 305, v: 0.02 }];
                pairs.forEach(({ f, v }) => {
                    const o = ctx.createOscillator();
                    const g = ctx.createGain();
                    o.type = "sine";
                    o.frequency.value = f;
                    g.gain.setValueAtTime(0, t);
                    g.gain.linearRampToValueAtTime(v, t + 0.04);
                    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.4);
                    o.connect(g); g.connect(out);
                    o.start(t); o.stop(t + 0.42);
                });
            }

        } catch (e) {
            // Audio is non-critical — swallow all errors silently
            void e;
        }
    }, []);

    return { playSound };
}
