"use client";

import { motion } from "framer-motion";

export function ForensicGrid() {
  return (
    <div className="absolute inset-0 z-0 pointer-events-none overflow-hidden select-none" aria-hidden="true">
      {/* Primary Grid Lines */}
      <div 
        className="absolute inset-0"
        style={{
          backgroundImage: `
            linear-gradient(to right, rgba(255,255,255,0.03) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(255,255,255,0.03) 1px, transparent 1px)
          `,
          backgroundSize: '60px 60px'
        }}
      />

      {/* Sub-Grid Lines (Detailed) */}
      <div 
        className="absolute inset-0 opacity-40"
        style={{
          backgroundImage: `
            linear-gradient(to right, rgba(34,211,238,0.02) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(34,211,238,0.02) 1px, transparent 1px)
          `,
          backgroundSize: '12px 12px'
        }}
      />

      {/* Rhythmic Scanline */}
      <motion.div
        animate={{ 
          top: ["-10%", "110%"],
        }}
        transition={{ 
          duration: 8, 
          repeat: Infinity, 
          ease: "linear" 
        }}
        className="absolute left-0 right-0 h-24 bg-gradient-to-b from-transparent via-cyan-500/[0.03] to-transparent opacity-50 z-[1]"
      />

      {/* Pulse Artifacts at Grid Intersections */}
      <div className="absolute inset-0">
        {[...Array(4)].map((_, i) => (
            <motion.div
                key={i}
                initial={{ opacity: 0, scale: 0 }}
                animate={{ 
                    opacity: [0, 0.15, 0],
                    scale: [0.8, 1.2, 0.8],
                }}
                transition={{ 
                    duration: 4, 
                    delay: i * 1.5,
                    repeat: Infinity,
                    ease: "easeInOut"
                }}
                className="absolute w-64 h-64 rounded-full bg-cyan-500/10 blur-3xl"
                style={{
                    top: `${20 + i * 20}%`,
                    left: `${15 + (i % 2) * 60}%`
                }}
            />
        ))}
      </div>

      {/* Bottom Vignette */}
      <div className="absolute inset-0 bg-gradient-to-t from-[#06090f] via-transparent to-transparent opacity-80" />
    </div>
  );
}
