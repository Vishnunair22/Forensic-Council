"use client";

import { useEffect } from "react";
import { AlertTriangle, RotateCcw, Home, ShieldAlert } from "lucide-react";
import { useRouter } from "next/navigation";
import { ZodError } from "zod";

/** True when the error originated from Zod schema validation (malformed report). */
function isZodError(err: unknown): err is ZodError {
  return err instanceof ZodError || (err instanceof Error && err.name === "ZodError");
}

/** True when the error looks like a network/HTTP failure (no data received). */
function isNetworkError(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  const msg = err.message.toLowerCase();
  return (
    msg.includes("network") ||
    msg.includes("fetch") ||
    msg.includes("failed to retrieve") ||
    msg.includes("timeout") ||
    msg.includes("econnrefused")
  );
}

export default function ResultError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const router = useRouter();

  useEffect(() => {
    console.error("Result page error:", error);
  }, [error]);

  const zodError = isZodError(error);
  const networkError = isNetworkError(error);

  const title = zodError
    ? "Report Schema Error"
    : networkError
      ? "Network Error"
      : "Report Render Error";

  const description = zodError
    ? "The server returned a report in an unexpected format. This may indicate a version mismatch between frontend and backend. Please retry or contact support."
    : networkError
      ? "Could not reach the backend to retrieve the report. Check your connection and retry."
      : error.message || "The forensic report data could not be rendered.";

  const icon = zodError ? (
    <ShieldAlert className="w-10 h-10 text-amber-400" />
  ) : (
    <AlertTriangle className="w-10 h-10 text-rose-400" />
  );

  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-6 text-center px-6">
      <div className="w-20 h-20 rounded-2xl flex items-center justify-center bg-white/[0.03] border border-white/[0.06]">
        {icon}
      </div>
      <div className="space-y-2 max-w-md">
        <h2 className="text-2xl font-bold text-foreground tracking-tight">
          {title}
        </h2>
        <p className="text-foreground/40 text-sm font-medium">{description}</p>
        {zodError && (
          <p className="text-foreground/25 text-xs mt-2 font-mono">
            {(error as ZodError).issues
              .slice(0, 3)
              .map((i) => i.path.join(".") + ": " + i.message)
              .join(" · ")}
          </p>
        )}
      </div>
      <div className="flex gap-3">
        <button
          onClick={reset}
          className="flex items-center gap-2 px-8 py-3 rounded-full text-xs font-black tracking-wide bg-amber-500/15 text-amber-300 border border-amber-500/25 hover:bg-amber-500/25 transition-all cursor-pointer"
        >
          <RotateCcw className="w-4 h-4" /> Retry
        </button>
        <button
          onClick={() => router.push("/")}
          className="flex items-center gap-2 px-8 py-3 rounded-full text-xs font-black tracking-wide text-foreground/50 border border-white/[0.07] bg-white/[0.03] hover:bg-white/[0.06] transition-all cursor-pointer"
        >
          <Home className="w-4 h-4" /> Home
        </button>
      </div>
    </div>
  );
}
