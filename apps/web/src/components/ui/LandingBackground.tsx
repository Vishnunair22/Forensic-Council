"use client";

export const LandingBackground = () => {
  return (
    <div 
      className="fixed inset-0 pointer-events-none z-0 overflow-hidden" 
      style={{ background: "#02040A" }}
      aria-hidden="true"
    >
      {/* Repeating micro-grid pattern */}
      <div 
        className="absolute inset-0 opacity-[0.015]"
        style={{
          backgroundImage: `
            linear-gradient(to right, rgba(255, 255, 255, 0.15) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(255, 255, 255, 0.15) 1px, transparent 1px)
          `,
          backgroundSize: "24px 24px"
        }}
      />
      {/* Teal radial glow top-left */}
      <div 
        className="absolute top-[-20%] left-[-10%] w-[60%] h-[60%] rounded-full filter blur-[120px] opacity-[0.04]"
        style={{
          background: "radial-gradient(circle, #14B8A6 0%, transparent 70%)"
        }}
      />
      {/* Muted slate-teal radial glow bottom-right */}
      <div 
        className="absolute bottom-[-20%] right-[-10%] w-[60%] h-[60%] rounded-full filter blur-[120px] opacity-[0.03]"
        style={{
          background: "radial-gradient(circle, #0f766e 0%, transparent 70%)"
        }}
      />
    </div>
  );
};
