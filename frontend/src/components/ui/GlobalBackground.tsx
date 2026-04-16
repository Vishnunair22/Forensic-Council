"use client";

/**
 * GlobalBackground: Static CSS mesh gradient with a slow breathing pulse.
 * Zero JS animation, zero canvas, zero CPU overhead.
 * The breathing effect is gated behind prefers-reduced-motion.
 */
export function GlobalBackground() {
  return (
    <div
      className="fixed inset-0 z-0 pointer-events-none"
      aria-hidden="true"
      style={{ background: "#080c14" }}
    >
      {/* Radial top-center glow — primary depth cue */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 80% 50% at 50% -10%, rgba(14,165,233,0.08) 0%, transparent 70%)",
        }}
      />

      {/* Bottom-right secondary accent */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 60% 40% at 90% 110%, rgba(16,185,129,0.04) 0%, transparent 60%)",
        }}
      />

      {/* Subtle dot grid substrate */}
      <div
        className="absolute inset-0"
        style={{
          backgroundImage:
            "radial-gradient(rgba(255,255,255,0.03) 1px, transparent 1px)",
          backgroundSize: "32px 32px",
        }}
      />

      {/* Slow breathing pulse — CSS only, gated on motion preference */}
      <div className="bg-pulse" />
    </div>
  );
}
