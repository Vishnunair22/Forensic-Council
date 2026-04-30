"use client";

import { useState, useEffect, useCallback } from "react";
import { storage } from "@/lib/storage";

export function useSessionStorage<T>(
  key: string,
  initialValue: T,
  parseJson = false
): [T, (val: T | ((prev: T) => T)) => void] {
  const readValue = useCallback(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return (storage.getItem(key, parseJson as any, initialValue as any) as T) ?? initialValue;
  }, [key, initialValue, parseJson]);

  const [state, setState] = useState<T>(readValue);

  useEffect(() => {
    setState(readValue());

    const handleStorageUpdate = (e: Event) => {
      const customEvent = e as CustomEvent<{ key: string; value: unknown }>;
      if (customEvent.detail.key === key) {
        setState(readValue());
      }
    };

    window.addEventListener("fc_storage_update", handleStorageUpdate);
    return () =>
      window.removeEventListener("fc_storage_update", handleStorageUpdate);
  }, [key, readValue]);

  const setValue = useCallback(
    (value: T | ((prev: T) => T)) => {
      const nextValue = value instanceof Function ? value(state) : value;
      setState(nextValue);
      storage.setItem(key, nextValue, parseJson);
    },
    [key, parseJson, state]
  );

  return [state, setValue];
}
