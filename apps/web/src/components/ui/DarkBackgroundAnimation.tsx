"use client";

import { motion, useScroll, useTransform, useSpring } from "framer-motion";
import { useEffect, useState, useRef } from "react";

/**
 * DarkBackgroundAnimation: A premium, subtle dark background with a 
 * flowing neural grid and floating forensic data particles.
 */
export function DarkBackgroundAnimation() {
  const { scrollYProgress } = useScroll();
  
  // Smooth out the scroll tracking
  const smoothYProgress = useSpring(scrollYProgress, {
    stiffness: 40,
    damping: 20,
    restDelta: 0.001
  });

  const gridY = useTransform(smoothYProgress, [0, 1], ["0%", "-20%"]);

  return (
    <div className="fixed inset-0 z-0 pointer-events-none overflow-hidden bg-[#020617]">
      {/* --- Ambient Background Grid --- */}
      <motion.div 
        style={{ y: gridY }}
        className="absolute inset-0 opacity-[0.15]"
      >
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#1e293b_1px,transparent_1px),linear-gradient(to_bottom,#1e293b_1px,transparent_1px)] bg-[size:60px_60px]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,#020617_100%)]" />
      </motion.div>
      
      {/* --- Pulsing Globs --- */}
      <div className="absolute inset-0 overflow-hidden">
        <motion.div 
          animate={{ 
            scale: [1, 1.2, 1],
            x: [0, 50, 0],
            y: [0, 30, 0],
          }}
          transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
          className="absolute -top-[10%] -left-[10%] w-[50%] h-[50%] bg-primary/5 blur-[120px] rounded-full"
        />
        <motion.div 
          animate={{ 
            scale: [1.2, 1, 1.2],
            x: [0, -40, 0],
            y: [0, -20, 0],
          }}
          transition={{ duration: 25, repeat: Infinity, ease: "linear" }}
          className="absolute -bottom-[10%] -right-[10%] w-[40%] h-[40%] bg-blue-500/5 blur-[120px] rounded-full"
        />
      </div>

      {/* --- Floating Particles --- */}
      <Particles />

      {/* --- Scanning Line (Subtle) --- */}
      <motion.div 
        animate={{ top: ["-10%", "110%"] }}
        transition={{ duration: 15, repeat: Infinity, ease: "linear" }}
        className="absolute left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-primary/20 to-transparent z-10"
      />

      {/* --- Vignette --- */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,rgba(2,6,23,0.9)_100%)]" />
    </div>
  );
}

function Particles() {
  const [particles, setParticles] = useState<{ id: number; x: number; y: number; size: number; duration: number }[]>([]);

  useEffect(() => {
    const p = Array.from({ length: 30 }).map((_, i) => ({
      id: i,
      x: Math.random() * 100,
      y: Math.random() * 100,
      size: Math.random() * 2 + 1,
      duration: Math.random() * 10 + 10,
    }));
    setParticles(p);
  }, []);

  return (
    <div className="absolute inset-0">
      {particles.map((p) => (
        <motion.div
          key={p.id}
          initial={{ opacity: 0 }}
          animate={{ 
            opacity: [0, 0.5, 0],
            y: [0, -100],
          }}
          transition={{ 
            duration: p.duration, 
            repeat: Infinity, 
            ease: "linear",
            delay: Math.random() * 10
          }}
          style={{
            left: `${p.x}%`,
            top: `${p.y}%`,
            width: p.size,
            height: p.size,
          }}
          className="absolute bg-primary rounded-full shadow-[0_0_8px_var(--color-primary)]"
        />
      ))}
    </div>
  );
}
