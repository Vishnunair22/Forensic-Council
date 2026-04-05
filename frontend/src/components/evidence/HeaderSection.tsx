"use client";

import { useRouter } from "next/navigation";
import { HistoryDrawer } from "@/components/ui/HistoryDrawer";

interface HeaderSectionProps {
  status: string;
  showBrowse: boolean;
  onBrowseClick: () => void;
}

export function HeaderSection({
  status,
  showBrowse,
  onBrowseClick,
}: HeaderSectionProps) {
  const router = useRouter();

  return (
    <header
      className="sticky top-3 max-w-6xl mx-auto flex items-center justify-between mb-6 z-50 px-5 py-3 rounded-2xl shadow-xl"
      style={{
        background: "rgba(3,11,26,0.80)",
        backdropFilter: "blur(24px)",
        WebkitBackdropFilter: "blur(24px)",
        border: "1px solid rgba(255,255,255,0.07)",
      }}
    >
      {/* Logo */}
      <button
        type="button"
        className="flex items-center gap-4 cursor-pointer group"
        onClick={() => {
          if (status !== "analyzing") router.push("/");
        }}
        aria-label="Return to Forensic Council home"
      >
        <div
          className="relative w-8 h-8 flex items-center justify-center rounded-lg transition-all duration-300 group-hover:shadow-[0_0_16px_rgba(34,211,238,0.25)]"
          style={{
            background: "rgba(34,211,238,0.08)",
            border: "1px solid rgba(34,211,238,0.18)",
          }}
        >
          <span
            className="font-black text-[10px] tracking-widest"
            style={{ color: "#22D3EE" }}
          >
            FC
          </span>
        </div>
        <div className="flex flex-col justify-center">
          <span className="text-[11px] font-black tracking-[0.1em] text-white block leading-tight uppercase transition-colors group-hover:text-cyan-300">
            Forensic Council
          </span>
          <span
            className="text-[8px] font-mono uppercase tracking-[0.3em] leading-relaxed font-bold"
            style={{ color: "rgba(34,211,238,0.45)" }}
          >
            Investigation Node
          </span>
        </div>
      </button>

      <div className="flex items-center gap-3">
        <HistoryDrawer />
        {showBrowse && (
          <button
            onClick={onBrowseClick}
            className="btn-premium-glass px-5 py-2"
            aria-label="Browse system for new evidence file"
          >
            Browse System
          </button>
        )}
      </div>
    </header>
  );
}
