"use client";

import React, { useEffect, useRef, useCallback, useState } from 'react';
import { createNoise2D } from 'simplex-noise';
import { cn } from '../../lib/utils';

export interface AnimatedWaveProps {
  className?: string;
  speed?: number;
  amplitude?: number;
  smoothness?: number;
  wireframe?: boolean;
  waveColor?: string;
  opacity?: number;
  mouseInteraction?: boolean;
  quality?: 'low' | 'medium' | 'high';
  backgroundColor?: string;
}

/**
 * Pure CSS/canvas animated wave — replaces the three.js version.
 * Uses HTML5 Canvas 2D with simplex noise for the wave displacement.
 * No WebGL or three.js dependency required.
 */
const AnimatedWave: React.FC<AnimatedWaveProps> = ({
  className,
  speed = 0.015,
  amplitude = 30,
  smoothness = 300,
  wireframe = true,
  waveColor,
  opacity = 1,
  mouseInteraction = true,
  quality = 'medium',
  backgroundColor,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animFrameRef = useRef<number>(0);
  const mouseRef = useRef({ x: 0, y: 0 });
  const cycleRef = useRef(0);

  const getSegments = useCallback(() => {
    switch (quality) {
      case "low": return 64;
      case "high": return 256;
      default: return 128;
    }
  }, [quality]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    resize();
    window.addEventListener("resize", resize);

    const noise2D = createNoise2D();
    const segments = getSegments();

    const handleMouse = (e: MouseEvent) => {
      mouseRef.current.x = e.clientX;
      mouseRef.current.y = e.clientY;
    };
    if (mouseInteraction) {
      window.addEventListener("mousemove", handleMouse);
    }

    const draw = () => {
      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);

      const factor = smoothness;
      const scale = amplitude;
      const cycle = cycleRef.current;
      cycleRef.current += speed;

      const rows = Math.floor(segments / 2);
      const cols = segments;
      const cellW = w / cols;
      const cellH = h / rows;

      ctx.strokeStyle = waveColor || "rgba(34, 211, 238, 0.3)";
      ctx.lineWidth = wireframe ? 0.8 : 0;
      ctx.globalAlpha = opacity;

      for (let r = 0; r < rows; r++) {
        ctx.beginPath();
        for (let c = 0; c <= cols; c++) {
          const baseX = c * cellW;
          const baseY = r * cellH;
          const nx = (baseX - w / 2) / factor;
          const ny = (baseY - h / 2) / factor + cycle;
          const z = noise2D(nx, ny) * scale;

          let finalX = baseX;
          let finalY = baseY + z * 0.5;

          if (mouseInteraction) {
            const dx = baseX - mouseRef.current.x;
            const dy = baseY - mouseRef.current.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            const radius = 200;
            if (dist < radius) {
              const falloff = 1 - dist / radius;
              finalX += dx * falloff * 0.1;
              finalY += dy * falloff * 0.1;
            }
          }

          if (c === 0) ctx.moveTo(finalX, finalY);
          else ctx.lineTo(finalX, finalY);
        }
        if (!wireframe) {
          ctx.lineTo(w, h);
          ctx.lineTo(0, h);
          ctx.closePath();
          ctx.fillStyle = waveColor || "rgba(34, 211, 238, 0.05)";
          ctx.fill();
        }
        ctx.stroke();
      }

      if (wireframe) {
        for (let c = 0; c <= cols; c++) {
          ctx.beginPath();
          for (let r = 0; r <= rows; r++) {
            const baseX = c * cellW;
            const baseY = r * cellH;
            const nx = (baseX - w / 2) / factor;
            const ny = (baseY - h / 2) / factor + cycle;
            const z = noise2D(nx, ny) * scale;
            const finalY = baseY + z * 0.5;
            if (r === 0) ctx.moveTo(baseX, finalY);
            else ctx.lineTo(baseX, finalY);
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
      if (mouseInteraction) window.removeEventListener("mousemove", handleMouse);
    };
  }, [getSegments, speed, amplitude, smoothness, wireframe, waveColor, opacity, mouseInteraction]);

  return (
    <div style={{ perspective: "900px" }}>
      <div
        className={cn(
          "relative w-full h-screen z-10 overflow-hidden",
          className
        )}
        style={{ pointerEvents: "none", backgroundColor: backgroundColor || "transparent" }}
      >
        <canvas
          ref={canvasRef}
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
        />
      </div>
    </div>
  );
};

export default AnimatedWave;
