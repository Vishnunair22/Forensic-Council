"use client";

export const LandingBackground = () => (
  <div className="fixed inset-0 overflow-hidden pointer-events-none z-0" aria-hidden="true">
    {/* Base */}
    <div className="absolute inset-0 bg-background" />

    {/* Architectural grid */}
    <div className="absolute inset-0 bg-dot-grid opacity-60" />

    {/* Primary ambient — top center */}
    <div
      className="absolute -top-[20%] left-1/2 -translate-x-1/2 w-[900px] h-[600px] rounded-full"
      style={{
        background: "radial-gradient(ellipse, rgba(56,120,240,0.09) 0%, transparent 65%)",
        filter: "blur(60px)",
      }}
    />

    {/* Secondary accent — bottom right */}
    <div
      className="absolute bottom-0 right-0 w-[600px] h-[400px]"
      style={{
        background: "radial-gradient(ellipse at 80% 100%, rgba(79,142,247,0.055) 0%, transparent 65%)",
        filter: "blur(50px)",
      }}
    />

    {/* Vignette — perimeter darkening */}
    <div
      className="absolute inset-0"
      style={{
        background: "radial-gradient(ellipse 120% 100% at 50% 50%, transparent 40%, rgba(2,4,10,0.7) 100%)",
      }}
    />

    {/* Top edge highlight */}
    <div
      className="absolute inset-x-0 top-0 h-px"
      style={{
        background: "linear-gradient(90deg, transparent 10%, rgba(79,142,247,0.3) 50%, transparent 90%)",
      }}
    />
  </div>
);
