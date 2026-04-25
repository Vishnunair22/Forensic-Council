"use client";

import { useCallback, useRef } from "react";

const isDev = process.env.NODE_ENV !== "production";

/**
 * useForensicSfx: Crystalline Audio Synthesis
 * 
 * Provides procedural, low-latency sound effects using the Web Audio API. 
 * Specifically tuned for 'Digital Hum' and 'Forensic Pulses.'
 */
export function useForensicSfx() {
  const audioCtxRef = useRef<AudioContext | null>(null);

  const initAudio = useCallback(() => {
    if (!audioCtxRef.current) {
      const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      audioCtxRef.current = new AudioCtx();
    }
    if (audioCtxRef.current.state === "suspended") {
      audioCtxRef.current.resume();
    }
    return audioCtxRef.current;
  }, []);

  /**
   * playHum: A subtle, low-frequency digital bloom.
   * tuned for interaction feedback (non-jarring).
   */
  const playHum = useCallback(() => {
    try {
      const ctx = initAudio();
      const now = ctx.currentTime;

      // Master Gain for overall volume control
      const masterGain = ctx.createGain();
      masterGain.gain.setValueAtTime(0, now);
      masterGain.gain.linearRampToValueAtTime(0.08, now + 0.05); // Rapid but soft bloom
      masterGain.gain.exponentialRampToValueAtTime(0.001, now + 0.3); // Smooth decay
      masterGain.connect(ctx.destination);

      // Low-frequency Oscillator (The Thrum)
      const osc = ctx.createOscillator();
      osc.type = "sine";
      osc.frequency.setValueAtTime(65.41, now); // C2 (Deep, subtle thrum)
      osc.frequency.exponentialRampToValueAtTime(40, now + 0.3); // Slight downward pitch glide
      
      osc.connect(masterGain);
      osc.start(now);
      osc.stop(now + 0.35);

      // High-frequency Crystalline "Ping" (for clarity)
      const pingGain = ctx.createGain();
      pingGain.gain.setValueAtTime(0, now);
      pingGain.gain.linearRampToValueAtTime(0.02, now + 0.01);
      pingGain.gain.exponentialRampToValueAtTime(0.001, now + 0.15);
      pingGain.connect(ctx.destination);

      const ping = ctx.createOscillator();
      ping.type = "sine";
      ping.frequency.setValueAtTime(880, now); // A5 (Clear, high-freq blink)
      
      ping.connect(pingGain);
      ping.start(now);
      ping.stop(now + 0.2);

    } catch (error) {
      if (isDev) console.warn("Forensic Audio synthesis failed:", error);
    }
  }, [initAudio]);

  /**
   * playSuccess: A positive, dual-tone harmonic bloom.
   * Provides confirmation for successful ingestion.
   */
  const playSuccess = useCallback(() => {
    try {
      const ctx = initAudio();
      const now = ctx.currentTime;

      const masterGain = ctx.createGain();
      masterGain.gain.setValueAtTime(0, now);
      masterGain.gain.linearRampToValueAtTime(0.1, now + 0.02);
      masterGain.gain.exponentialRampToValueAtTime(0.001, now + 0.4);
      masterGain.connect(ctx.destination);

      // Root Harmonic (Warmth)
      const osc1 = ctx.createOscillator();
      osc1.type = "sine";
      osc1.frequency.setValueAtTime(261.63, now); // C4
      osc1.frequency.exponentialRampToValueAtTime(329.63, now + 0.1); // Slide to E4
      
      // Upper Partial (Clarity/Success)
      const osc2 = ctx.createOscillator();
      osc2.type = "sine";
      osc2.frequency.setValueAtTime(523.25, now); // C5
      osc2.frequency.exponentialRampToValueAtTime(783.99, now + 0.15); // Slide to G5
      
      osc1.connect(masterGain);
      osc2.connect(masterGain);
      
      osc1.start(now);
      osc2.start(now);
      osc1.stop(now + 0.4);
      osc2.stop(now + 0.4);

    } catch (error) {
      if (isDev) console.warn("Forensic Success SFX failed:", error);
    }
  }, [initAudio]);

  return { playHum, playSuccess };
}
