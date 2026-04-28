"use client";

import { useCallback, useEffect, useState } from "react";
import { getMuted, setMasterVolume, setMuted } from "./useSound";

const STORAGE_KEY = "forensic_sound_muted";
const DEFAULT_VOLUME = 0.3;

export function useSoundscape() {
  const [isMuted, setIsMuted] = useState(false);
  const [volume, setVolume] = useState(DEFAULT_VOLUME);

  useEffect(() => {
    if (typeof window === "undefined") return;

    // Auto-mute when user prefers reduced motion
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setMuted(true);
      setIsMuted(true);
      return;
    }

    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored !== null) {
      const muted = stored === "true";
      setMuted(muted);
      setIsMuted(muted);
    }

    setMasterVolume(DEFAULT_VOLUME);
    setVolume(DEFAULT_VOLUME);
  }, []);

  const toggleMute = useCallback(() => {
    const next = !getMuted();
    setMuted(next);
    setIsMuted(next);
    if (typeof window !== "undefined") {
      localStorage.setItem(STORAGE_KEY, String(next));
    }
  }, []);

  const changeVolume = useCallback((v: number) => {
    const clamped = Math.max(0, Math.min(1, v));
    setMasterVolume(clamped);
    setVolume(clamped);
  }, []);

  return { isMuted, volume, toggleMute, changeVolume };
}
