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
  const lensScale = useTransform(smoothYProgress, [0, 0.5, 1], [1, 1.04, 1]);
  const lensRotate = useTransform(smoothYProgress, [0, 1], [0, 180]);

  return (
    <div className="fixed inset-0 z-0 pointer-events-none overflow-hidden bg-black">
      {/* --- Ambient Background --- */}
      <div className="absolute inset-0 bg-grid-small opacity-[0.05]" />
      
      {/* --- Scanning Laser --- */}
      <motion.div 
        style={{ top: lensY }}
        className="absolute left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-primary/40 to-transparent z-10 shadow-[0_0_15px_rgba(0,255,65,0.3)]"
      >
        <div className="absolute top-0 left-0 right-0 h-[50px] bg-gradient-to-b from-primary/5 to-transparent -translate-y-full" />
      </motion.div>
      
      {/* --- Digital Evidence Nodes --- */}
      <EvidenceNodes progress={smoothYProgress} />

      {/* --- Microscope Lens --- */}
      <motion.div
        style={{
          top: lensY,
          left: "50%",
          translateX: "-50%",
          translateY: "-50%",
          scale: lensScale,
        }}
        className="absolute w-[450px] h-[450px] md:w-[700px] md:h-[700px] z-20"
      >
        {/* Outer Lens Frame (Technical) */}
        <div className="absolute inset-0 rounded-full border border-primary/15 bg-primary/5 backdrop-blur-[4px] shadow-[0_0_120px_rgba(0,255,65,0.1)]" />
        <div className="absolute inset-[2px] rounded-full border border-white/5" />
        
        {/* Inner Lens Details (Grid + Crosshairs) */}
        <motion.div 
          style={{ rotate: lensRotate }}
          className="absolute inset-8 rounded-full border border-primary/10 flex items-center justify-center"
        >
          {/* Main Axis */}
          <div className="w-full h-[1px] bg-primary/30" />
          <div className="absolute w-[1px] h-full bg-primary/30" />
          
          {/* Technical Grid */}
          <div className="absolute inset-0 opacity-20" style={{ backgroundImage: 'radial-gradient(var(--color-primary) 0.5px, transparent 0.5px)', backgroundSize: '20px 20px' }} />
          
          {/* Concentric Circles with Scale Marks */}
          {[1, 0.75, 0.5, 0.25].map((scale, i) => (
            <div key={i} className="absolute rounded-full border border-primary/10" style={{ width: `${scale * 100}%`, height: `${scale * 100}%` }}>
               <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-full text-[8px] font-mono text-primary/40 pt-1">
                 {Math.round(scale * 1000)}µm
               </div>
            </div>
          ))}
          
          {/* Tactical Marks */}
          {Array.from({ length: 12 }).map((_, i) => (
            <div
              key={i}
              className="absolute w-6 h-[1px] bg-primary/50"
              style={{ transform: `rotate(${i * 30}deg) translateX(320px)` }}
            />
          ))}
        </motion.div>

        {/* The "Liquid Glass" Reflection */}
        <div className="absolute inset-0 rounded-full bg-gradient-to-br from-white/10 via-transparent to-primary/5 opacity-60 mix-blend-overlay" />
        <div className="absolute top-[10%] left-[10%] w-[40%] h-[40%] rounded-full bg-gradient-to-br from-white/20 to-transparent blur-2xl opacity-30" />
        
        {/* Focal Point Data */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 flex flex-col items-center">
            <div className="w-4 h-4 rounded-full bg-primary shadow-[0_0_20px_var(--color-primary)] animate-pulse" />
        </div>
      </motion.div>

      {/* --- Procedural Noise/Grain --- */}
      <svg className="absolute inset-0 w-full h-full opacity-[0.06] mix-blend-overlay">
        <filter id="microNoise">
          <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="3" stitchTiles="stitch" />
        </filter>
        <rect width="100%" height="100%" filter="url(#microNoise)" />
      </svg>
    </div>
  );
}

function EvidenceNodes({ progress }: { progress: import("framer-motion").MotionValue<number> }) {
  const [nodes, setNodes] = useState<{ id: number; x: number; y: number; label: string }[]>([]);

  useEffect(() => {
    const labels = ["METADATA_CORRUPT", "DIFFUSION_SIGNAL", "ELA_OUTLIER", "JPEG_GHOST", "SIFT_MATCH", "C2PA_MISSING"];
    const n = Array.from({ length: 15 }).map((_, i) => ({
      id: i,
      x: 10 + Math.random() * 80,
      y: 10 + Math.random() * 80,
      label: labels[i % labels.length],
    }));
    setNodes(n);
  }, []);

  return (
    <div className="absolute inset-0">
      {nodes.map((node) => (
        <EvidenceNode key={node.id} node={node} progress={progress} />
      ))}
    </div>
  );
}

interface NodeData {
  id: number;
  x: number;
  y: number;
  label: string;
}

function EvidenceNode({ node, progress }: { node: NodeData; progress: import("framer-motion").MotionValue<number> }) {
  const yShift = useTransform(progress, [0, 1], [0, -100]);
  
  return (
    <motion.div
      style={{
        left: `${node.x}%`,
        top: `${node.y}%`,
        y: yShift,
      }}
      className="absolute flex flex-col items-center group"
    >
      <div className="w-1.5 h-1.5 bg-primary/20 rounded-full border border-primary/40 group-hover:bg-primary transition-colors" />
      <div className="mt-2 px-1.5 py-0.5 bg-black/40 border border-white/5 rounded text-[8px] font-mono text-white/30 group-hover:text-primary/60 transition-colors">
        {node.label}
      </div>
    </motion.div>
  );
}

