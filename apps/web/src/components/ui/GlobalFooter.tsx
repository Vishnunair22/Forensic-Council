"use client";

/**
 * GlobalFooter: Universal footer for the Horizon theme.
 * Keeps original disclaimer text while adding forensic telemetry styling.
 */
export function GlobalFooter() {
  return (
    <footer className="w-full py-16 px-8 relative z-[100] bg-transparent mt-auto overflow-hidden">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-8">
        <div className="hidden md:block text-[9px] font-mono tracking-[0.4em] text-white/50 uppercase font-bold">
          Council_Bridge_2.0
        </div>

        <div className="text-[10px] font-mono tracking-widest text-white/60 uppercase">
          &copy; 2024 Forensic Council
        </div>

        <div className="hidden md:block text-[9px] font-mono tracking-[0.4em] text-white/50 uppercase font-bold">
          Node_Status: Active
        </div>
      </div>
    </footer>
  );
}
