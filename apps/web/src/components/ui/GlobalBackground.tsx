"use client";

/**
 * GlobalBackground: Static CSS mesh gradient with a slow breathing pulse.
 * Minimal overhead, cinematic depth.
 */
export function GlobalBackground() {
  return (
    <div
      className="fixed inset-0 z-0 pointer-events-none overflow-hidden"
      aria-hidden="true"
      style={{ background: "#020617" }}
    >
      {/* Top Center Ambient Glow (Cyan) */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 70% 50% at 50% -10%, rgba(6, 182, 212, 0.08) 0%, transparent 70%)",
        }}
      />

      {/* Bottom Right Subtle Resolve (Emerald) */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 60% 40% at 90% 110%, rgba(16, 185, 129, 0.04) 0%, transparent 60%)",
        }}
      />

      {/* Tactile Dot Grid Substrate */}
      <div
        className="absolute inset-0 opacity-[0.15]"
        style={{
          backgroundImage:
            "radial-gradient(rgba(255, 255, 255, 0.1) 1px, transparent 1px)",
          backgroundSize: "40px 40px",
        }}
      />

      {/* Center Soft Focal Point */}
      <div
        className="absolute inset-0"
        style={{
          background: "radial-gradient(circle at 50% 50%, rgba(6, 182, 212, 0.02) 0%, transparent 50%)"
        }}
      />

      {/* Procedural Grain Texture (Premium Overlay) */}
      <svg className="fixed inset-0 w-full h-full opacity-[0.03] pointer-events-none mix-blend-overlay z-[1]">
        <filter id="grainy">
          <feTurbulence type="fractalNoise" baseFrequency="0.65" numOctaves="3" stitchTiles="stitch" />
        </filter>
        <rect width="100%" height="100%" filter="url(#grainy)" />
      </svg>

      {/* Breathing Effect Background Layer */}
      <div className="absolute inset-0 bg-pulse opacity-20 pointer-events-none z-0" />
    </div>
  );
}
