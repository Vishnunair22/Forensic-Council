"use client";

import { motion, useScroll, useTransform, useSpring } from "framer-motion";
import { useEffect, useState } from "react";

/**
 * MicroscopeBackground: A high-fidelity animated background featuring a 
 * "Microscope Lens" that tracks the user's scroll position.
 */
export function MicroscopeBackground() {
  const { scrollYProgress } = useScroll();
  
  // Smooth out the scroll tracking
  const smoothYProgress = useSpring(scrollYProgress, {
    stiffness: 100,
    damping: 30,
    restDelta: 0.001
  });

  const lensY = useTransform(smoothYProgress, [0, 1], ["10%", "90%"]);
  const lensScale = useTransform(smoothYProgress, [0, 0.5, 1], [1, 1.2, 1]);
  const lensRotate = useTransform(smoothYProgress, [0, 1], [0, 360]);

  return (
    <div className="fixed inset-0 z-0 pointer-events-none overflow-hidden bg-[#020617]">
      {/* --- Ambient Background --- */}
      <div className="absolute inset-0 bg-grid-small opacity-[0.1]" />
      
      {/* --- Floating Evidence Particles --- */}
      <EvidenceParticles progress={smoothYProgress} />

      {/* --- Microscope Lens --- */}
      <motion.div
        style={{
          top: lensY,
          left: "50%",
          translateX: "-50%",
          translateY: "-50%",
          scale: lensScale,
        }}
        className="absolute w-[400px] h-[400px] md:w-[600px] md:h-[600px] z-20"
      >
        {/* Outer Lens Frame */}
        <div className="absolute inset-0 rounded-full border border-primary/20 bg-primary/5 backdrop-blur-[2px] shadow-[0_0_100px_rgba(34,211,238,0.1)]" />
        
        {/* Inner Lens Details (Grid + Crosshairs) */}
        <motion.div 
          style={{ rotate: lensRotate }}
          className="absolute inset-4 rounded-full border border-primary/10 flex items-center justify-center"
        >
          {/* Horizontal Line */}
          <div className="w-full h-[1px] bg-primary/20" />
          {/* Vertical Line */}
          <div className="absolute w-[1px] h-full bg-primary/20" />
          
          {/* Concentric Circles */}
          <div className="absolute w-1/2 h-1/2 rounded-full border border-primary/10" />
          <div className="absolute w-3/4 h-3/4 rounded-full border border-primary/10" />
          
          {/* Tactical Marks */}
          {[0, 90, 180, 270].map((deg) => (
            <div
              key={deg}
              className="absolute w-4 h-[2px] bg-primary/40"
              style={{ transform: `rotate(${deg}deg) translateX(280px)` }}
            />
          ))}
        </motion.div>

        {/* The "Glass" Reflection/Glint */}
        <div className="absolute inset-0 rounded-full bg-gradient-to-tr from-transparent via-white/5 to-white/10 opacity-40" />
        
        {/* Focal Point Glow */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-4 h-4 rounded-full bg-primary blur-sm animate-pulse" />
      </motion.div>

      {/* --- Procedural Noise/Grain --- */}
      <svg className="absolute inset-0 w-full h-full opacity-[0.04] mix-blend-overlay">
        <filter id="microNoise">
          <feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="4" stitchTiles="stitch" />
        </filter>
        <rect width="100%" height="100%" filter="url(#microNoise)" />
      </svg>
    </div>
  );
}

interface Particle {
  id: number;
  x: number;
  y: number;
  size: number;
  delay: number;
  speed: number;
}

function EvidenceParticles({ progress }: { progress: import("framer-motion").MotionValue<number> }) {
  const [particles, setParticles] = useState<Particle[]>([]);
  const yShift = useTransform(progress, [0, 1], [0, -50]);

  useEffect(() => {
    // Generate static particles on mount
    const p = Array.from({ length: 20 }).map((_, i) => ({
      id: i,
      x: Math.random() * 100,
      y: Math.random() * 100,
      size: Math.random() * 4 + 2,
      delay: Math.random() * 5,
      speed: Math.random() * 2 + 1,
    }));
    setParticles(p);
  }, []);

  return (
    <motion.div style={{ y: yShift }} className="absolute inset-0">
      {particles.map((p) => (
        <motion.div
          key={p.id}
          initial={{ opacity: 0 }}
          animate={{ 
            opacity: [0.1, 0.4, 0.1],
            y: [p.y + "%", (p.y - 10) + "%", p.y + "%"]
          }}
          transition={{
            duration: p.speed * 5,
            repeat: Infinity,
            delay: p.delay,
            ease: "easeInOut"
          }}
          style={{
            left: p.x + "%",
            width: p.size,
            height: p.size,
          }}
          className="absolute bg-primary/30 rounded-full blur-[1px]"
        />
      ))}
    </motion.div>
  );
}
