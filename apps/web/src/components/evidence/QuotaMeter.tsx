"use client";

import React, { useEffect, useState } from "react";
import { TrendingUp, AlertTriangle, XCircle, DollarSign } from "lucide-react";

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
      if (!mounted) return;
      setLoading(true);

      try {
        const token = document.cookie
          .split("; ")
          .find((row) => row.startsWith("access_token="))
          ?.split("=")[1];

        const response = await fetch(`/api/v1/sessions/${sessionId}/quota`, {
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

    // Poll every 5 seconds during active analysis
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
      <div className="flex items-center gap-2 text-xs text-amber-600">
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

  const getStatusColor = () => {
    if (isCritical) return "bg-red-500";
    if (isWarning) return "bg-amber-500";
    return "bg-emerald-500";
  };

  const getStatusTextColor = () => {
    if (isCritical) return "text-red-700";
    if (isWarning) return "text-amber-700";
    return "text-emerald-700";
  };

  return (
    <div className="flex items-center gap-3 px-3 py-1.5 rounded-md bg-muted/50 text-xs">
      <div className="flex items-center gap-1.5">
        <TrendingUp className={`h-3.5 w-3.5 ${getStatusTextColor()}`} />
        <span className="font-medium text-muted-foreground">Quota:</span>
      </div>

      <div className="flex items-center gap-2">
        <div className="w-24 h-2 rounded-full bg-muted-foreground/20 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-300 ${getStatusColor()}`}
            style={{ width: `${usagePercent}%` }}
          />
        </div>
        <span className={getStatusTextColor()}>
          {quota.tokens_used.toLocaleString()} / {quota.tokens_limit.toLocaleString()}
        </span>
      </div>

      <div className="flex items-center gap-1 text-muted-foreground">
        <DollarSign className="h-3 w-3" />
        <span>${quota.cost_estimate_usd.toFixed(4)}</span>
      </div>

      <div className="flex items-center gap-1 text-muted-foreground">
        <span>{quota.calls_total} calls</span>
      </div>

      {isCritical && (
        <div className="flex items-center gap-1 text-red-600">
          <XCircle className="h-3 w-3" />
          <span className="font-medium">Limit reached</span>
        </div>
      )}

      {isWarning && !isCritical && (
        <div className="flex items-center gap-1 text-amber-600">
          <AlertTriangle className="h-3 w-3" />
          <span className="font-medium">High usage</span>
        </div>
      )}
    </div>
  );
}
