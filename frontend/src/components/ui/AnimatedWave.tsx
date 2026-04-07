"use client";

import React, { useEffect, useRef, useCallback, memo } from "react";
import { createNoise2D } from "simplex-noise";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export interface AnimatedWaveProps {
  className?: string;
  speed?: number;
  amplitude?: number;
  smoothness?: number;
  wireframe?: boolean;
  waveColor?: string;
  opacity?: number;
  quality?: "low" | "medium" | "high";
  backgroundColor?: string;
}

/**
 * Optimized Forensic Waveform Background.
 * Uses a throttle-aware canvas draw loop and reduced vertex segments for performance.
 */
const AnimatedWave: React.FC<AnimatedWaveProps> = memo(({
  className,
  speed = 0.01,
  amplitude = 25,
  smoothness = 350,
  wireframe = true,
  waveColor = "rgba(34, 211, 238, 0.4)",
  opacity = 0.6,
  quality = "medium",
  backgroundColor = "transparent",
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animFrameRef = useRef<number>(0);
  const cycleRef = useRef(0);

  const getSegments = useCallback(() => {
    switch (quality) {
      case "low": return 48;
      case "high": return 128;
      default: return 80;
    }
  }, [quality]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) return;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      canvas.width = window.innerWidth * dpr;
      canvas.height = window.innerHeight * dpr;
      ctx.scale(dpr, dpr);
    };
    resize();
    window.addEventListener("resize", resize);

    const noise2D = createNoise2D();
    const segments = getSegments();
    const rows = Math.floor(segments / 2.5);
    const cols = segments;

    const draw = () => {
      const w = window.innerWidth;
      const h = window.innerHeight;
      ctx.clearRect(0, 0, w, h);

      const factor = smoothness;
      const scale = amplitude;
      cycleRef.current += speed;
      const cycle = cycleRef.current;

      const cellW = w / cols;
      const cellH = h / rows;

      ctx.strokeStyle = waveColor;
      ctx.lineWidth = 0.7;
      ctx.globalAlpha = opacity;

      // Draw rows - optimized loop
      for (let r = 0; r <= rows; r++) {
        ctx.beginPath();
        for (let c = 0; c <= cols; c++) {
          const x = c * cellW;
          const y = r * cellH;
          const nx = (x - w / 2) / factor;
          const ny = (y - h / 2) / factor + cycle;
          const z = noise2D(nx, ny) * scale;

          if (c === 0) ctx.moveTo(x, y + z);
          else ctx.lineTo(x, y + z);
        }
        ctx.stroke();
      }

      // Draw cols (wireframe) - draw less frequently or simpler
      if (wireframe) {
        ctx.globalAlpha = opacity * 0.5;
        for (let c = 0; c <= cols; c += 2) { // Draw every 2nd column for performance
          ctx.beginPath();
          for (let r = 0; r <= rows; r++) {
            const x = c * cellW;
            const y = r * cellH;
            const nx = (x - w / 2) / factor;
            const ny = (y - h / 2) / factor + cycle;
            const z = noise2D(nx, ny) * scale;
            if (r === 0) ctx.moveTo(x, y + z);
            else ctx.lineTo(x, y + z);
          }
          ctx.stroke();
        }
      }

      animFrameRef.current = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      cancelAnimationFrame(animFrameRef.current);
      window.removeEventListener("resize", resize);
    };
  }, [getSegments, speed, amplitude, smoothness, wireframe, waveColor, opacity]);

  return (
    <div
      className={cn("fixed inset-0 -z-50 pointer-events-none overflow-hidden", className)}
      style={{ backgroundColor }}
    >
      <canvas
        ref={canvasRef}
        aria-hidden="true"
        className="w-full h-full"
        style={{ opacity }}
      />
    </div>
  );
});

export default AnimatedWave;
