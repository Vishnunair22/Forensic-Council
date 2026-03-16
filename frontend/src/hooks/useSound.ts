"use client";

import { useCallback } from "react";

export type SoundType = "success" | "error" | "agent" | "complete" | "think" | "click" | "upload" | "envelope_open" | "envelope_close" | "scan";

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

            } else if (type === "envelope_open") {
                // Paper rustle (band-pass noise burst) + mechanical latch click
                // 1. White noise "paper" burst — 80 ms
                const bufLen = Math.ceil(ctx.sampleRate * 0.08);
                const noiseBuffer = ctx.createBuffer(1, bufLen, ctx.sampleRate);
                const d = noiseBuffer.getChannelData(0);
                for (let i = 0; i < bufLen; i++) d[i] = (Math.random() * 2 - 1) * 0.4;
                const noiseSource = ctx.createBufferSource();
                noiseSource.buffer = noiseBuffer;
                // Band-pass filter — paper "swish" frequency range
                const bpf = ctx.createBiquadFilter();
                bpf.type = "bandpass";
                bpf.frequency.value = 1800;
                bpf.Q.value = 1.5;
                const ng = ctx.createGain();
                ng.gain.setValueAtTime(0, t);
                ng.gain.linearRampToValueAtTime(0.25, t + 0.01);
                ng.gain.exponentialRampToValueAtTime(0.0001, t + 0.08);
                noiseSource.connect(bpf); bpf.connect(ng); ng.connect(out);
                noiseSource.start(t); noiseSource.stop(t + 0.09);
                // 2. Latch click — short sine transient at 1200 Hz, 30 ms
                const latch = ctx.createOscillator();
                const lg = ctx.createGain();
                latch.type = "sine";
                latch.frequency.setValueAtTime(1200, t + 0.06);
                latch.frequency.exponentialRampToValueAtTime(400, t + 0.09);
                lg.gain.setValueAtTime(0, t + 0.06);
                lg.gain.linearRampToValueAtTime(0.06, t + 0.065);
                lg.gain.exponentialRampToValueAtTime(0.0001, t + 0.1);
                latch.connect(lg); lg.connect(out);
                latch.start(t + 0.06); latch.stop(t + 0.11);
                // 3. Rising confirmation tone — C5→E5, 250 ms, soft
                [523.25, 659.25].forEach((freq, i) => {
                    const delay = 0.05 + i * 0.1;
                    const o = ctx.createOscillator();
                    const g = createSoftGain(ctx, 0.032, 0.01, 0.2);
                    o.type = "triangle";
                    o.frequency.value = freq;
                    o.connect(g); g.connect(out);
                    o.start(t + delay); o.stop(t + delay + 0.24);
                });

            } else if (type === "envelope_close") {
                // Reverse: brief descending tone + soft paper close
                [523.25, 392].forEach((freq, i) => {
                    const delay = i * 0.08;
                    const o = ctx.createOscillator();
                    const g = createSoftGain(ctx, 0.025, 0.008, 0.15);
                    o.type = "sine";
                    o.frequency.value = freq;
                    o.connect(g); g.connect(out);
                    o.start(t + delay); o.stop(t + delay + 0.18);
                });
                // Soft noise close
                const bufLen2 = Math.ceil(ctx.sampleRate * 0.06);
                const nb2 = ctx.createBuffer(1, bufLen2, ctx.sampleRate);
                const d2 = nb2.getChannelData(0);
                for (let i = 0; i < bufLen2; i++) d2[i] = (Math.random() * 2 - 1) * 0.3;
                const ns2 = ctx.createBufferSource();
                ns2.buffer = nb2;
                const bf2 = ctx.createBiquadFilter();
                bf2.type = "bandpass"; bf2.frequency.value = 1200; bf2.Q.value = 1.2;
                const ng2 = ctx.createGain();
                ng2.gain.setValueAtTime(0.18, t + 0.12);
                ng2.gain.exponentialRampToValueAtTime(0.0001, t + 0.2);
                ns2.connect(bf2); bf2.connect(ng2); ng2.connect(out);
                ns2.start(t + 0.12); ns2.stop(t + 0.22);

            } else if (type === "scan") {
                // Electronic scan sweep: FM chirp 300→1800 Hz, 600 ms, soft
                const o = ctx.createOscillator();
                const g = ctx.createGain();
                o.type = "sawtooth";
                o.frequency.setValueAtTime(300, t);
                o.frequency.exponentialRampToValueAtTime(1800, t + 0.5);
                // HP filter to make it cleaner
                const hp = ctx.createBiquadFilter();
                hp.type = "highpass"; hp.frequency.value = 600;
                g.gain.setValueAtTime(0, t);
                g.gain.linearRampToValueAtTime(0.02, t + 0.05);
                g.gain.linearRampToValueAtTime(0.015, t + 0.45);
                g.gain.exponentialRampToValueAtTime(0.0001, t + 0.6);
                o.connect(hp); hp.connect(g); g.connect(out);
                o.start(t); o.stop(t + 0.62);
            }

        } catch (e) {
            // Audio is non-critical — swallow all errors silently
            void e;
        }
    }, []);

    return { playSound };
}
