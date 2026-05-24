"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { storage } from "@/lib/storage";

export function usePersistentStorage<T>(
  key: string,
  initialValue: T,
  parseJson = false
): [T, (val: T | ((prev: T) => T)) => void] {
  // Stabilize initialValue so a caller passing a literal `[]` or `{}` on every render
  // doesn't cause readValue to change reference → effect re-runs → infinite re-render loop.
  const initialValueRef = useRef(initialValue);

  const readValue = useCallback(() => {
    const fallback = initialValueRef.current;
    const val = parseJson
      ? storage.getItem(key, true, fallback)
      : storage.getItem(key, false, fallback as unknown as string);
    return (val as T | null) ?? fallback;
  }, [key, parseJson]);

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
      setState((prev) => {
        const nextValue = value instanceof Function ? value(prev) : value;
        storage.setItem(key, nextValue, parseJson);
        return nextValue;
      });
    },
    [key, parseJson]
  );

  return [state, setValue];
}
