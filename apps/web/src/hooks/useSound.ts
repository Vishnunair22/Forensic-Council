"use client";

import { useCallback } from "react";

export type SoundType =
  | "envelope-open"
  | "envelope-close"
  | "success-chime"
  | "envelope_open"
  | "envelope_close"
  | "success"
  | "error"
  | "agent"
  | "complete"
  | "think"
  | "click"
  | "upload"
  | "scan"
  | "page_load"
  | "analysis_done"
  | "arbiter_start"
  | "arbiter_done"
  | "result_reveal"
  | "hum";

let globalCtx: AudioContext | null = null;
// Chrome's autoplay policy: AudioContext must be created/resumed after a user gesture.
// We set this flag on the first qualifying DOM event and create the context then.
let _audioUnlocked = false;

type AudioContextConstructor = new () => AudioContext;

function _tryUnlock() {
  if (_audioUnlocked) return;
  _audioUnlocked = true;
  try {
    if (typeof window === "undefined") return;
    const AC =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: AudioContextConstructor })
        .webkitAudioContext;
    if (AC && !globalCtx) globalCtx = new AC();
    if (globalCtx?.state === "suspended") globalCtx.resume().catch(() => {});
  } catch {
    /* non-critical */
  }
}

// Register once — removes itself after the first gesture.
if (typeof window !== "undefined") {
  const _once = () => {
    _tryUnlock();
    window.removeEventListener("pointerdown", _once, true);
  };
  window.addEventListener("pointerdown", _once, {
    capture: true,
    passive: true,
  });
}

/** Soft gain envelope helper — attack + exponential release */
function createSoftGain(
  ctx: AudioContext,
  peakGain: number,
  attackTime: number,
  releaseTime: number,
): GainNode {
  const g = ctx.createGain();
  g.gain.setValueAtTime(0, ctx.currentTime);
  g.gain.linearRampToValueAtTime(peakGain, ctx.currentTime + attackTime);
  g.gain.exponentialRampToValueAtTime(
    0.0001,
    ctx.currentTime + attackTime + releaseTime,
  );
  return g;
}

export function useSound() {
  const playSound = useCallback((type: SoundType) => {
    try {
      if (typeof window === "undefined") return;
      // Only proceed if user has already interacted — prevents the Chrome
      // "AudioContext was not allowed to start" warning on programmatic calls.
      if (!_audioUnlocked || !globalCtx) return;

      const ctx = globalCtx;
      if (!ctx) return;

      if (ctx.state === "suspended") ctx.resume().catch(() => {});

      const t = ctx.currentTime;

      // ── Master limiter ────────────────────────────────────────────────────
      const limiter = ctx.createDynamicsCompressor();
      limiter.threshold.value = -6;
      limiter.knee.value = 6;
      limiter.ratio.value = 10;
      limiter.attack.value = 0.003;
      limiter.release.value = 0.1;
      limiter.connect(ctx.destination);

      const out = limiter;

      // ── Sounds ────────────────────────────────────────────────────────────

      if (type === "click") {
        // Ultra-subtle: single sine tick, 60 ms
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.type = "sine";
        o.frequency.value = 880;
        g.gain.setValueAtTime(0, t);
        g.gain.linearRampToValueAtTime(0.028, t + 0.005);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.06);
        o.connect(g);
        g.connect(out);
        o.start(t);
        o.stop(t + 0.07);
      } else if (type === "upload" || type === "success" || type === "success-chime") {
        // Mock Design Sync: Rising 523 -> 1046Hz sine
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.type = "sine";
        o.frequency.setValueAtTime(523.25, t);
        o.frequency.exponentialRampToValueAtTime(1046.5, t + 0.1);
        g.gain.setValueAtTime(0.1, t);
        g.gain.exponentialRampToValueAtTime(0.01, t + 0.3);
        o.connect(g);
        g.connect(out);
        o.start(t);
        o.stop(t + 0.3);
      } else if (type === "agent") {
        // Mock Design Sync: Triangle blip at 440Hz
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.type = "triangle";
        o.frequency.setValueAtTime(440, t);
        g.gain.setValueAtTime(0.05, t);
        g.gain.exponentialRampToValueAtTime(0.01, t + 0.1);
        o.connect(g);
        g.connect(out);
        o.start(t);
        o.stop(t + 0.1);
      } else if (type === "think") {
        // Mock Design Sync: Subtle 220Hz sine blip
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.type = "sine";
        o.frequency.setValueAtTime(220, t);
        g.gain.setValueAtTime(0.02, t);
        g.gain.exponentialRampToValueAtTime(0.001, t + 0.05);
        o.connect(g);
        g.connect(out);
        o.start(t);
        o.stop(t + 0.05);
      } else if (type === "complete") {
        // Mock Design Sync: Rising 440->880Hz sine
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.type = "sine";
        o.frequency.setValueAtTime(440, t);
        o.frequency.exponentialRampToValueAtTime(880, t + 0.2);
        g.gain.setValueAtTime(0.1, t);
        g.gain.exponentialRampToValueAtTime(0.01, t + 0.5);
        o.connect(g);
        g.connect(out);
        o.start(t);
        o.stop(t + 0.5);
      } else if (type === "error") {
        // Gentle dissonance: two detuned sines, 400 ms
        [
          { f: 320, v: 0.03 },
          { f: 305, v: 0.02 },
        ].forEach(({ f, v }) => {
          const o = ctx.createOscillator();
          const g = ctx.createGain();
          o.type = "sine";
          o.frequency.value = f;
          g.gain.setValueAtTime(0, t);
          g.gain.linearRampToValueAtTime(v, t + 0.04);
          g.gain.exponentialRampToValueAtTime(0.0001, t + 0.4);
          o.connect(g);
          g.connect(out);
          o.start(t);
          o.stop(t + 0.42);
        });
      } else if (type === "envelope_open" || type === "envelope-open") {
        // Paper swish + latch click + C5→E5 confirmation tone
        const bufLen = Math.ceil(ctx.sampleRate * 0.08);
        const noiseBuffer = ctx.createBuffer(1, bufLen, ctx.sampleRate);
        const d = noiseBuffer.getChannelData(0);
        for (let i = 0; i < bufLen; i++) d[i] = (Math.random() * 2 - 1) * 0.4;
        const ns = ctx.createBufferSource();
        ns.buffer = noiseBuffer;
        const bpf = ctx.createBiquadFilter();
        bpf.type = "bandpass";
        bpf.frequency.value = 1800;
        bpf.Q.value = 1.5;
        const ng = ctx.createGain();
        ng.gain.setValueAtTime(0, t);
        ng.gain.linearRampToValueAtTime(0.25, t + 0.01);
        ng.gain.exponentialRampToValueAtTime(0.0001, t + 0.08);
        ns.connect(bpf);
        bpf.connect(ng);
        ng.connect(out);
        ns.start(t);
        ns.stop(t + 0.09);
        const latch = ctx.createOscillator();
        const lg = ctx.createGain();
        latch.type = "sine";
        latch.frequency.setValueAtTime(1200, t + 0.06);
        latch.frequency.exponentialRampToValueAtTime(400, t + 0.09);
        lg.gain.setValueAtTime(0, t + 0.06);
        lg.gain.linearRampToValueAtTime(0.06, t + 0.065);
        lg.gain.exponentialRampToValueAtTime(0.0001, t + 0.1);
        latch.connect(lg);
        lg.connect(out);
        latch.start(t + 0.06);
        latch.stop(t + 0.11);
        [523.25, 659.25].forEach((freq, i) => {
          const delay = 0.05 + i * 0.1;
          const o = ctx.createOscillator();
          const g = createSoftGain(ctx, 0.032, 0.01, 0.2);
          o.type = "triangle";
          o.frequency.value = freq;
          o.connect(g);
          g.connect(out);
          o.start(t + delay);
          o.stop(t + delay + 0.24);
        });
      } else if (type === "envelope_close" || type === "envelope-close") {
        // Descending C5→G4 + soft paper close
        [523.25, 392].forEach((freq, i) => {
          const delay = i * 0.08;
          const o = ctx.createOscillator();
          const g = createSoftGain(ctx, 0.025, 0.008, 0.15);
          o.type = "sine";
          o.frequency.value = freq;
          o.connect(g);
          g.connect(out);
          o.start(t + delay);
          o.stop(t + delay + 0.18);
        });
        const bufLen2 = Math.ceil(ctx.sampleRate * 0.06);
        const nb2 = ctx.createBuffer(1, bufLen2, ctx.sampleRate);
        const d2 = nb2.getChannelData(0);
        for (let i = 0; i < bufLen2; i++) d2[i] = (Math.random() * 2 - 1) * 0.3;
        const ns2 = ctx.createBufferSource();
        ns2.buffer = nb2;
        const bf2 = ctx.createBiquadFilter();
        bf2.type = "bandpass";
        bf2.frequency.value = 1200;
        bf2.Q.value = 1.2;
        const ng2 = ctx.createGain();
        ng2.gain.setValueAtTime(0.18, t + 0.12);
        ng2.gain.exponentialRampToValueAtTime(0.0001, t + 0.2);
        ns2.connect(bf2);
        bf2.connect(ng2);
        ng2.connect(out);
        ns2.start(t + 0.12);
        ns2.stop(t + 0.22);
      } else if (type === "scan") {
        // Modern scan-activate: clean rising tone + soft noise burst, 500 ms
        // Sine sweep 420 → 1400 Hz with quick onset — cleaner than sawtooth
        const sweep = ctx.createOscillator();
        const sweepGain = ctx.createGain();
        sweep.type = "sine";
        sweep.frequency.setValueAtTime(420, t);
        sweep.frequency.exponentialRampToValueAtTime(1400, t + 0.38);
        sweepGain.gain.setValueAtTime(0, t);
        sweepGain.gain.linearRampToValueAtTime(0.022, t + 0.04);
        sweepGain.gain.linearRampToValueAtTime(0.012, t + 0.34);
        sweepGain.gain.exponentialRampToValueAtTime(0.0001, t + 0.46);
        sweep.connect(sweepGain);
        sweepGain.connect(out);
        sweep.start(t);
        sweep.stop(t + 0.48);
        // Subtle HF noise burst at the start — "system activated" feel
        const bufLen = Math.ceil(ctx.sampleRate * 0.06);
        const nb = ctx.createBuffer(1, bufLen, ctx.sampleRate);
        const d = nb.getChannelData(0);
        for (let i = 0; i < bufLen; i++) d[i] = (Math.random() * 2 - 1) * 0.05;
        const ns = ctx.createBufferSource();
        ns.buffer = nb;
        const hpf = ctx.createBiquadFilter();
        hpf.type = "highpass";
        hpf.frequency.value = 3200;
        const ng = ctx.createGain();
        ng.gain.setValueAtTime(0.12, t);
        ng.gain.exponentialRampToValueAtTime(0.0001, t + 0.07);
        ns.connect(hpf);
        hpf.connect(ng);
        ng.connect(out);
        ns.start(t);
        ns.stop(t + 0.08);
      } else if (type === "page_load") {
        // Electronic system init: HF noise burst + rising sine chirp 200 → 900 Hz
        const bufLen = Math.ceil(ctx.sampleRate * 0.12);
        const nb = ctx.createBuffer(1, bufLen, ctx.sampleRate);
        const d = nb.getChannelData(0);
        for (let i = 0; i < bufLen; i++) d[i] = (Math.random() * 2 - 1) * 0.1;
        const ns = ctx.createBufferSource();
        ns.buffer = nb;
        const hpf = ctx.createBiquadFilter();
        hpf.type = "highpass";
        hpf.frequency.value = 2600;
        const ng = ctx.createGain();
        ng.gain.setValueAtTime(0, t);
        ng.gain.linearRampToValueAtTime(0.09, t + 0.02);
        ng.gain.exponentialRampToValueAtTime(0.0001, t + 0.14);
        ns.connect(hpf);
        hpf.connect(ng);
        ng.connect(out);
        ns.start(t);
        ns.stop(t + 0.15);
        // Rising chirp
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.type = "sine";
        o.frequency.setValueAtTime(200, t + 0.04);
        o.frequency.exponentialRampToValueAtTime(900, t + 0.3);
        g.gain.setValueAtTime(0, t + 0.04);
        g.gain.linearRampToValueAtTime(0.02, t + 0.08);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.34);
        o.connect(g);
        g.connect(out);
        o.start(t + 0.04);
        o.stop(t + 0.36);
      } else if (type === "analysis_done") {
        // Ascending 4-note arpeggio: C4 E4 G4 C5 — satisfying major progression
        const NOTES = [261.63, 329.63, 392.0, 523.25];
        NOTES.forEach((freq, i) => {
          const delay = i * 0.1;
          const o = ctx.createOscillator();
          const g = ctx.createGain();
          o.type = i === 3 ? "triangle" : "sine";
          o.frequency.value = freq;
          g.gain.setValueAtTime(0, t + delay);
          g.gain.linearRampToValueAtTime(0.044, t + delay + 0.012);
          g.gain.exponentialRampToValueAtTime(0.0001, t + delay + 0.85);
          o.connect(g);
          g.connect(out);
          o.start(t + delay);
          o.stop(t + delay + 0.9);
        });
      } else if (type === "arbiter_start") {
        // Deep authoritative chord: G2 G3 D4 bass + mystery band-pass shimmer
        const BASS = [98.0, 196.0, 293.66];
        BASS.forEach((freq, i) => {
          const delay = i * 0.07;
          const o = ctx.createOscillator();
          const g = ctx.createGain();
          o.type = "sine";
          o.frequency.value = freq;
          const peak = i === 0 ? 0.05 : 0.026;
          g.gain.setValueAtTime(0, t + delay);
          g.gain.linearRampToValueAtTime(peak, t + delay + 0.18);
          g.gain.linearRampToValueAtTime(peak * 0.52, t + 0.78);
          g.gain.exponentialRampToValueAtTime(0.0001, t + 1.05);
          o.connect(g);
          g.connect(out);
          o.start(t + delay);
          o.stop(t + 1.1);
        });
        // Mystery band-pass shimmer
        const bufLen = Math.ceil(ctx.sampleRate * 0.35);
        const nb = ctx.createBuffer(1, bufLen, ctx.sampleRate);
        const d = nb.getChannelData(0);
        for (let i = 0; i < bufLen; i++) d[i] = (Math.random() * 2 - 1) * 0.055;
        const ns = ctx.createBufferSource();
        ns.buffer = nb;
        const bpf = ctx.createBiquadFilter();
        bpf.type = "bandpass";
        bpf.frequency.value = 680;
        bpf.Q.value = 4.5;
        const ng = ctx.createGain();
        ng.gain.setValueAtTime(0, t + 0.22);
        ng.gain.linearRampToValueAtTime(0.03, t + 0.32);
        ng.gain.exponentialRampToValueAtTime(0.0001, t + 0.6);
        ns.connect(bpf);
        bpf.connect(ng);
        ng.connect(out);
        ns.start(t + 0.22);
        ns.stop(t + 0.65);
      } else if (type === "arbiter_done") {
        // Dignified G-major resolution: G4 B4 D5 G5 triangle waves, long sustain
        const CHORD = [392.0, 493.88, 587.33, 783.99];
        CHORD.forEach((freq, i) => {
          const delay = i * 0.08;
          const o = ctx.createOscillator();
          const g = ctx.createGain();
          o.type = "triangle";
          o.frequency.value = freq;
          g.gain.setValueAtTime(0, t + delay);
          g.gain.linearRampToValueAtTime(0.038, t + delay + 0.012);
          g.gain.exponentialRampToValueAtTime(0.0001, t + delay + 1.2);
          o.connect(g);
          g.connect(out);
          o.start(t + delay);
          o.stop(t + delay + 1.25);
        });
      } else if (type === "result_reveal") {
        // Upward glissando 280 → 1200 Hz + crystalline C6 ding
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.type = "sine";
        o.frequency.setValueAtTime(280, t);
        o.frequency.exponentialRampToValueAtTime(1200, t + 0.36);
        g.gain.setValueAtTime(0, t);
        g.gain.linearRampToValueAtTime(0.018, t + 0.05);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.44);
        o.connect(g);
        g.connect(out);
        o.start(t);
        o.stop(t + 0.46);
        // Crystal C6 ding
        const o2 = ctx.createOscillator();
        const g2 = createSoftGain(ctx, 0.038, 0.008, 0.6);
        o2.type = "triangle";
        o2.frequency.value = 1046.5;
        o2.connect(g2);
        g2.connect(out);
        o2.start(t + 0.28);
        o2.stop(t + 0.76);
      } else if (type === "hum") {
        const masterGain = ctx.createGain();
        masterGain.gain.setValueAtTime(0, t);
        masterGain.gain.linearRampToValueAtTime(0.08, t + 0.05);
        masterGain.gain.exponentialRampToValueAtTime(0.001, t + 0.3);
        masterGain.connect(out);
        const osc = ctx.createOscillator();
        osc.type = "sine";
        osc.frequency.setValueAtTime(65.41, t);
        osc.frequency.exponentialRampToValueAtTime(40, t + 0.3);
        osc.connect(masterGain);
        osc.start(t);
        osc.stop(t + 0.35);
        const pingGain = ctx.createGain();
        pingGain.gain.setValueAtTime(0, t);
        pingGain.gain.linearRampToValueAtTime(0.02, t + 0.01);
        pingGain.gain.exponentialRampToValueAtTime(0.001, t + 0.15);
        pingGain.connect(out);
        const ping = ctx.createOscillator();
        ping.type = "sine";
        ping.frequency.setValueAtTime(880, t);
        ping.connect(pingGain);
        ping.start(t);
        ping.stop(t + 0.2);
      }
    } catch (e: unknown) {
      // Audio is non-critical — swallow all errors silently
      void e;
    }
  }, []);

  return { playSound };
}
