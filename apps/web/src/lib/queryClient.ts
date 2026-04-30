"use client";

import { QueryClient } from "@tanstack/react-query";

/**
 * Shared QueryClient configuration for Forensic Council.
 *
 * Retry policy: do not retry on 4xx (auth/not-found errors are not transient).
 * Only retry on network failures (no response) or 5xx.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // 30 seconds before data is considered stale
        staleTime: 30_000,
        // Do not cache indefinitely — 5 minutes
        gcTime: 5 * 60_000,
        retry: (failureCount, error) => {
          // Never retry client errors (4xx)
          if (error instanceof Error && "status" in error) {
            const status = (error as { status: number }).status;
            if (status >= 400 && status < 500) return false;
          }
          return failureCount < 2;
        },
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: false,
      },
    },
  });
}
