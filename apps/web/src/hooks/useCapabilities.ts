"use client";

import { useEffect, useState } from "react";
import { setServerCapabilities, type ServerCapabilities } from "@/lib/agentSupport";
import { API_BASE } from "@/lib/api/utils";

export function useCapabilities(): { capabilities: ServerCapabilities | null; loading: boolean } {
  const [capabilities, setCapabilities] = useState<ServerCapabilities | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function fetchCaps() {
      // 10s timeout so a slow/dead backend can't leave agent filtering stuck
      // on the loading branch indefinitely — it falls back to the static map.
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 10000);
      try {
        const resp = await fetch(`${API_BASE}/api/v1/capabilities`, {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!resp.ok) return;
        const data: ServerCapabilities = await resp.json();
        if (!cancelled) {
          setCapabilities(data);
          setServerCapabilities(data);
        }
      } catch {
        // Non-critical (timeout or network) — fall back to static mapping
      } finally {
        clearTimeout(timeout);
        if (!cancelled) setLoading(false);
      }
    }

    fetchCaps();
    return () => { cancelled = true; };
  }, []);

  return { capabilities, loading };
}
