"use client";

import { motion, useScroll, useTransform, useSpring, useMotionValue, useAnimationFrame } from "framer-motion";
import { useEffect, useState, useRef } from "react";

/**
 * MicroscopeBackground: A high-fidelity animated background featuring a 
 * "Blue Horizon" lens with chromatic aberration, magnetic lag, and metadata ticker.
 */
export function MicroscopeBackground() {
  const { scrollYProgress } = useScroll();
  const containerRef = useRef<HTMLDivElement>(null);
  
  // Magnetic Lag: Smooth out the scroll tracking with spring physics
  const smoothYProgress = useSpring(scrollYProgress, {
    stiffness: 40,
    damping: 20,
    restDelta: 0.001
  });

  const lensY = useTransform(smoothYProgress, [0, 1], ["15%", "85%"]);
  const lensScale = useTransform(smoothYProgress, [0, 0.5, 1], [1, 1.1, 1]);
  
  return (
    <div ref={containerRef} className="fixed inset-0 z-0 pointer-events-none overflow-hidden bg-[#020617]">
      {/* --- Ambient Background Grid --- */}
      <div className="absolute inset-0 bg-grid-small opacity-[0.08]" />
      
      {/* --- Scanning Laser (The "Beam") --- */}
      <motion.div 
        style={{ top: lensY }}
        className="absolute left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-primary/60 to-transparent z-10 shadow-[0_0_20px_rgba(0,255,255,0.5)]"
      >
        <div className="absolute top-0 left-0 right-0 h-[100px] bg-gradient-to-b from-primary/10 to-transparent -translate-y-full" />
      </motion.div>
      
      {/* --- Digital Evidence Nodes --- */}
      <EvidenceNodes progress={smoothYProgress} />

      {/* --- Microscope Lens (Horizon Spec) --- */}
      <motion.div
        style={{
          top: lensY,
          left: "50%",
          translateX: "-50%",
          translateY: "-50%",
          scale: lensScale,
        }}
        className="absolute w-[400px] h-[400px] md:w-[650px] md:h-[650px] z-20"
      >
        {/* Outer Lens Frame with Bevel */}
        <div className="absolute inset-0 rounded-full border border-primary/20 bg-primary/5 backdrop-blur-[12px] shadow-[0_0_100px_rgba(0,255,255,0.15)]">
          {/* Chromatic Aberration Fringe */}
          <div className="absolute inset-0 rounded-full border-t-2 border-primary/30 blur-[2px]" />
          <div className="absolute inset-0 rounded-full border-b-2 border-danger/20 blur-[2px]" />
        </div>
        
        {/* Metadata Ticker (Side of Lens) */}
        <MetadataTicker />
        
        {/* Inner Lens HUD Details */}
        <div className="absolute inset-10 rounded-full border border-primary/10 flex items-center justify-center overflow-hidden">
          {/* Crosshairs */}
          <div className="w-full h-[0.5px] bg-primary/40" />
          <div className="absolute w-[0.5px] h-full bg-primary/40" />
          
          {/* Tactical Rotation Marks */}
          <motion.div 
            animate={{ rotate: 360 }}
            transition={{ duration: 60, repeat: Infinity, ease: "linear" }}
            className="absolute inset-0"
          >
            {Array.from({ length: 24 }).map((_, i) => (
              <div
                key={i}
                className="absolute w-4 h-[1px] bg-primary/30"
                style={{ 
                  left: "50%", 
                  top: "50%", 
                  transform: `rotate(${i * 15}deg) translateX(${typeof window !== 'undefined' && window.innerWidth < 768 ? '160px' : '280px'})` 
                }}
              />
            ))}
          </motion.div>
          
          {/* Focusing Grid */}
          <div className="absolute inset-0 opacity-[0.15]" 
               style={{ backgroundImage: 'radial-gradient(var(--color-primary) 0.5px, transparent 0.5px)', backgroundSize: '15px 15px' }} />
        </div>

        {/* Central Lock-on Reticle */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2">
           <motion.div 
             animate={{ scale: [1, 1.2, 1], opacity: [0.4, 0.8, 0.4] }}
             transition={{ duration: 2, repeat: Infinity }}
             className="w-6 h-6 border-2 border-primary rounded-sm flex items-center justify-center"
           >
             <div className="w-1 h-1 bg-primary rounded-full" />
           </motion.div>
        </div>
      </motion.div>

      {/* --- Procedural Noise/Grain --- */}
      <div className="absolute inset-0 opacity-[0.03] pointer-events-none mix-blend-overlay bg-noise" />
      
      {/* --- Vignette (Focus Effect) --- */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,rgba(2,6,23,0.8)_100%)]" />
    </div>
  );
}

function MetadataTicker() {
  const [codes, setCodes] = useState<string[]>([]);
  
  useEffect(() => {
    const generateCode = () => `0x${Math.random().toString(16).slice(2, 10).toUpperCase()}`;
    setCodes(Array.from({ length: 8 }).map(generateCode));
    
    const interval = setInterval(() => {
      setCodes(prev => [generateCode(), ...prev.slice(0, 7)]);
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="absolute -right-24 top-1/2 -translate-y-1/2 hidden lg:flex flex-col gap-2 font-mono text-[10px] text-primary/40">
      {codes.map((code, i) => (
        <motion.div 
          key={code + i}
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1 - i * 0.12, x: 0 }}
          className="tracking-widest"
        >
          {code}
        </motion.div>
      ))}
      <div className="h-[1px] w-12 bg-primary/20 mt-2" />
      <div className="text-[8px] uppercase tracking-tighter text-primary/20">Telemetry_Active</div>
    </div>
  );
}

function EvidenceNodes({ progress }: { progress: any }) {
  const [nodes, setNodes] = useState<{ id: number; x: number; y: number; label: string }[]>([]);

  useEffect(() => {
    const labels = ["DIFFUSION_SIGNAL", "METADATA_INTEGRITY", "ELA_ANALYSIS", "SIFT_DESCRIPTOR", "C2PA_SIGNED", "LLM_REASONING"];
    const n = Array.from({ length: 12 }).map((_, i) => ({
      id: i,
      x: 15 + Math.random() * 70,
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

function EvidenceNode({ node, progress }: { node: any; progress: any }) {
  const yShift = useTransform(progress, [0, 1], [0, -150]);
  const opacity = useTransform(progress, [node.y / 100 - 0.1, node.y / 100, node.y / 100 + 0.1], [0.2, 1, 0.2]);
  
  return (
    <motion.div
      style={{
        left: `${node.x}%`,
        top: `${node.y}%`,
        y: yShift,
        opacity
      }}
      className="absolute flex flex-col items-center"
    >
      <div className="w-1.5 h-1.5 bg-primary shadow-[0_0_8px_var(--color-primary)] rounded-full" />
      <div className="mt-2 px-2 py-0.5 border border-primary/20 bg-surface-1 rounded text-[9px] font-mono text-primary/60 backdrop-blur-sm">
        {node.label}
      </div>
    </motion.div>
  );
}
