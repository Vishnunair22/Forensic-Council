"use client";

import { useEffect } from "react";
import { AlertTriangle, RotateCcw, Home } from "lucide-react";
import { useRouter } from "next/navigation";

export default function EvidenceError({
 error,
 reset,
}: {
 error: Error & { digest?: string };
 reset: () => void;
}) {
 const router = useRouter();

 useEffect(() => {
  console.error("Evidence page error:", error);
 }, [error]);

 return (
  <div className="min-h-screen flex flex-col items-center justify-center gap-6 text-center px-6">
   <div className="w-20 h-20 rounded-2xl flex items-center justify-center bg-white/[0.03] border border-white/[0.06]">
    <AlertTriangle className="w-10 h-10 text-amber-400" />
   </div>
   <div className="space-y-2 max-w-md">
    <h2 className="text-2xl font-bold text-foreground tracking-tight">
     Analysis Interrupted
    </h2>
    <p className="text-foreground/40 text-sm font-medium">
     {error.message ||
      "An unexpected error occurred during evidence processing."}
    </p>
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
