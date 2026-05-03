"use client";

import { useState, useEffect, useRef } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { createQueryClient } from "@/lib/queryClient";

function BackendWarmer() {
  const warmed = useRef(false);
  useEffect(() => {
    if (warmed.current) return;
    warmed.current = true;
    fetch("/api/v1/health", { method: "GET", cache: "no-store" }).catch(() => {});
  }, []);
  return null;
}

/**
 * Wraps the application with React Query's QueryClientProvider.
 *
 * A single QueryClient instance is created per browser session (via useState)
 * so it is not re-created on every render, but also not shared between
 * different server-side requests in RSC.
 */
export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => createQueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      <BackendWarmer />
      {children}
      {process.env.NODE_ENV === "development" && (
        <ReactQueryDevtools initialIsOpen={false} />
      )}
    </QueryClientProvider>
  );
}
