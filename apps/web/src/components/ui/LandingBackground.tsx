export const LandingBackground = () => {
  return (
    <div
      className="fixed inset-0 pointer-events-none overflow-hidden"
      style={{ zIndex: -10, background: "var(--color-background)" }}
      aria-hidden="true"
    >
      {/* Ambient glow — top-left */}
      <div
        className="absolute top-[-20%] left-[-10%] w-[60%] h-[60%] rounded-full opacity-[0.04]"
        style={{
          background: "radial-gradient(circle, var(--color-primary) 0%, transparent 70%)",
          filter: "blur(120px)",
        }}
      />
      {/* Ambient glow — bottom-right */}
      <div
        className="absolute bottom-[-20%] right-[-10%] w-[60%] h-[60%] rounded-full opacity-[0.03]"
        style={{
          background: "radial-gradient(circle, var(--color-primary) 0%, transparent 70%)",
          filter: "blur(120px)",
        }}
      />
    </div>
  );
};
