export const LandingBackground = () => {
  return (
    <div
      className="fixed inset-0 pointer-events-none overflow-hidden"
      style={{ zIndex: -10, background: "var(--color-background)" }}
      aria-hidden="true"
    >
      {/* Aurora crown — top-center anchor that gives the hero headline a stage.
          Static (no animation): the design system bans ambient shimmer. */}
      <div
        className="absolute top-[-30%] left-1/2 -translate-x-1/2 w-[130%] sm:w-[90%] h-[62%] rounded-full opacity-[0.09]"
        style={{
          background:
            "radial-gradient(ellipse at 50% 45%, var(--color-primary-soft) 0%, var(--color-primary) 38%, transparent 72%)",
          filter: "blur(110px)",
        }}
      />
      {/* Ambient glow — top-left */}
      <div
        className="absolute top-[-20%] left-[-10%] w-[60%] h-[60%] rounded-full opacity-[0.05]"
        style={{
          background: "radial-gradient(circle, var(--color-primary) 0%, transparent 70%)",
          filter: "blur(120px)",
        }}
      />
      {/* Ambient glow — bottom-right */}
      <div
        className="absolute bottom-[-20%] right-[-10%] w-[60%] h-[60%] rounded-full opacity-[0.04]"
        style={{
          background: "radial-gradient(circle, var(--color-primary) 0%, transparent 70%)",
          filter: "blur(120px)",
        }}
      />
      {/* Edge vignette — darkens the frame to pull focus center. Pure gradient
          (no blur layer), and it only ever darkens, so text contrast at the
          edges improves rather than degrades. */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse at 50% 38%, transparent 55%, rgba(2,4,10,0.6) 100%)",
        }}
      />
    </div>
  );
};
