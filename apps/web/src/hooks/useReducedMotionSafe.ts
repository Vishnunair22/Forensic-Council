"use client";

import { useEffect, useState } from "react";
import { useReducedMotion } from "framer-motion";

/**
 * Hydration-safe wrapper around framer-motion's `useReducedMotion`.
 *
 * `useReducedMotion` returns `null` during SSR but the real OS/browser value on
 * the client. Branching `initial`/`animate` directly on it makes the server and
 * the client's first paint render different style/transform attributes on a
 * motion element — React then warns "a tree hydrated but some attributes … didn't
 * match" and discards that subtree (which can also drop event handlers, causing
 * intermittent dead clicks). This returns `false` (assume motion) until after
 * mount so the first client render matches the server, then switches to the real
 * preference on a subsequent render (animated normally, post-hydration).
 */
export function useReducedMotionSafe(): boolean {
  const reduced = useReducedMotion();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  return mounted ? !!reduced : false;
}
