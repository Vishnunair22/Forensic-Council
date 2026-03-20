import Link from "next/link";
import { ShieldAlert, Home, ArrowLeft } from "lucide-react";

export default function NotFound() {
  return (
    <div className="min-h-screen bg-[#030308] text-white flex flex-col items-center justify-center p-6 text-center relative overflow-hidden">
      {/* Background */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(99,102,241,0.06),transparent_60%)] pointer-events-none" />
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff03_1px,transparent_1px),linear-gradient(to_bottom,#ffffff03_1px,transparent_1px)] bg-[size:40px_40px] pointer-events-none" />

      <div className="relative z-10 max-w-md w-full flex flex-col items-center gap-6">
        {/* Icon */}
        <div className="w-20 h-20 rounded-2xl bg-indigo-500/10 border border-indigo-500/25 flex items-center justify-center shadow-[0_0_40px_rgba(99,102,241,0.15)]">
          <ShieldAlert className="w-10 h-10 text-indigo-400" />
        </div>

        {/* Headline */}
        <div className="space-y-2">
          <p className="text-indigo-400 font-mono text-xs tracking-[0.2em] uppercase">404 — Route Not Found</p>
          <h1 className="text-3xl font-black text-white tracking-tight">Page Not Found</h1>
          <p className="text-slate-500 text-sm leading-relaxed max-w-xs mx-auto">
            This route does not exist. The investigation system only serves
            defined forensic pipeline endpoints.
          </p>
        </div>

        {/* Actions */}
        <div className="flex flex-col sm:flex-row gap-3 w-full">
          <Link href="/" className="btn btn-violet flex-1 py-3 rounded-xl font-medium">
            <Home className="w-4 h-4" aria-hidden="true" />
            Dashboard
          </Link>
          <Link href="/evidence" className="btn btn-ghost flex-1 py-3 rounded-xl">
            <ArrowLeft className="w-4 h-4" aria-hidden="true" />
            New Investigation
          </Link>
        </div>
      </div>
    </div>
  );
}
