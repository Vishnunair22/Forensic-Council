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
      {/* Top Center Ambient Glow (Primary Cyan) */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 70% 60% at 50% -15%, rgba(0, 255, 65, 0.1) 0%, transparent 80%)",
        }}
      />

      {/* Bottom Right Ambient Glow (Accent Violet) */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 60% 50% at 85% 115%, rgba(139, 92, 246, 0.12) 0%, transparent 70%)",
        }}
      />

      {/* High-Density Tactile Dot Grid */}
      <div
        className="absolute inset-0 opacity-[0.2]"
        style={{
          backgroundImage:
            "radial-gradient(rgba(0, 255, 65, 0.1) 1px, transparent 1px)",
          backgroundSize: "32px 32px",
        }}
      />

      {/* Center Cinematic Focal Point */}
      <div
        className="absolute inset-0"
        style={{
          background: "radial-gradient(circle at 50% 50%, rgba(0, 255, 65, 0.05) 0%, transparent 60%)"
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
