"use client";

import React, { useEffect, useState } from "react";
import { TrendingUp, AlertTriangle, XCircle, DollarSign } from "lucide-react";
import { API_BASE } from "@/lib/api";

interface QuotaData {
  tokens_used: number;
  tokens_limit: number;
  cost_estimate_usd: number;
  calls_total: number;
  degraded: boolean;
}

interface QuotaMeterProps {
  sessionId: string | null;
  enabled?: boolean;
}

export function QuotaMeter({ sessionId, enabled = true }: QuotaMeterProps) {
  const [quota, setQuota] = useState<QuotaData | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!sessionId || !enabled) {
      setQuota(null);
      return;
    }

    let mounted = true;
    let pollInterval: NodeJS.Timeout | null = null;

    const fetchQuota = async () => {
      if (!mounted || typeof document === "undefined") return;
      if (document.visibilityState === "hidden") return;
      setLoading(true);

      try {
        const token = document.cookie
          .split("; ")
          .find((row) => row.startsWith("access_token="))
          ?.split("=")[1];

        const response = await fetch(`${API_BASE}/api/v1/sessions/${encodeURIComponent(sessionId)}/quota`, {
          headers: {
            Authorization: token ? `Bearer ${token}` : "",
          },
          credentials: "include",
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        if (mounted) {
          setQuota(data);
        }
      } catch {
        if (mounted) {
          setQuota({ tokens_used: 0, tokens_limit: 100000, cost_estimate_usd: 0, calls_total: 0, degraded: true });
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };

    // Initial fetch
    fetchQuota();

    // Poll every 5 seconds when visible, slow down when hidden
    pollInterval = setInterval(fetchQuota, 5000);

    return () => {
      mounted = false;
      if (pollInterval) {
        clearInterval(pollInterval);
      }
    };
  }, [sessionId, enabled]);

  if (!enabled || !sessionId) {
    return null;
  }

  if (loading && !quota) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <TrendingUp className="h-3 w-3 animate-pulse" />
        <span>Loading quota...</span>
      </div>
    );
  }

  if (quota?.degraded) {
    return (
      <div className="flex items-center gap-2 text-xs text-warning">
        <AlertTriangle className="h-3 w-3" />
        <span>Quota data unavailable</span>
      </div>
    );
  }

  if (!quota) {
    return null;
  }

  const usagePercent = Math.min((quota.tokens_used / quota.tokens_limit) * 100, 100);
  const isWarning = usagePercent >= 80;
  const isCritical = usagePercent >= 100;

  // A-H-2: Tailwind 700-tier shades fail WCAG AA contrast on dark surfaces.
  // Semantic tokens map to the brand-validated foreground hues.
  const getStatusTextColor = () => {
    if (isCritical) return "text-danger";
    if (isWarning) return "text-warning";
    return "text-success";
  };

  return (
    <div className="flex items-center gap-4 px-4 py-2 border border-white/10 bg-[#02040A] text-[10px] font-mono tracking-widest uppercase rounded">
      <div className="flex items-center gap-2">
        <TrendingUp className={`h-3.5 w-3.5 ${getStatusTextColor()}`} />
        <span className="text-white/50">Quota:</span>
        <span className={getStatusTextColor()}>
          {quota.tokens_used.toLocaleString()} / {quota.tokens_limit.toLocaleString()}
        </span>
      </div>

      <div className="w-px h-3 bg-white/10" aria-hidden="true" />

      <div className="flex items-center gap-1 text-white/50">
        <DollarSign className="h-3 w-3" />
        <span>${quota.cost_estimate_usd.toFixed(4)}</span>
      </div>

      <div className="w-px h-3 bg-white/10" aria-hidden="true" />

      <div className="flex items-center gap-1 text-white/50">
        <span>{quota.calls_total} calls</span>
      </div>

      {isCritical && (
        <>
          <div className="w-px h-3 bg-white/10" aria-hidden="true" />
          <div className="flex items-center gap-1 text-[var(--color-danger)] font-bold">
            <XCircle className="h-3 w-3" />
            <span>Limit reached</span>
          </div>
        </>
      )}

      {isWarning && !isCritical && (
        <>
          <div className="w-px h-3 bg-white/10" aria-hidden="true" />
          <div className="flex items-center gap-1 text-[var(--color-warning)] font-bold">
            <AlertTriangle className="h-3 w-3" />
            <span>High usage</span>
          </div>
        </>
      )}
    </div>
  );
}
