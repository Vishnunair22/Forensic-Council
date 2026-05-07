"use client";

export const LandingBackground = () => (
  <div className="fixed inset-0 overflow-hidden pointer-events-none z-0">
    <div className="absolute inset-0 bg-background" />
    <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(59,130,246,0.12)_0%,rgba(3,4,8,0)_36%,rgba(96,165,250,0.07)_100%)]" />
    <div className="absolute inset-0 bg-grid-small opacity-70" />
    <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(255,255,255,0.08),transparent_42%)]" />
  </div>
);
