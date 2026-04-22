"use client";

import { useState, useEffect, useCallback } from "react";

/**
 * Custom hook to track elapsed time
 * @param isActive Whether the timer should be running
 * @returns { elapsedTime: number, formattedTime: string, reset: () => void }
 */
export function useTimer(isActive: boolean) {
  const [elapsedTime, setElapsedTime] = useState(0);

  useEffect(() => {
    let interval: NodeJS.Timeout | null = null;

    if (isActive) {
      interval = setInterval(() => {
        setElapsedTime((prev) => prev + 1);
      }, 1000);
    } else {
      if (interval) clearInterval(interval);
    }

    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isActive]);

  const reset = useCallback(() => {
    setElapsedTime(0);
  }, []);

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  return {
    elapsedTime,
    formattedTime: formatTime(elapsedTime),
    reset,
  };
}
