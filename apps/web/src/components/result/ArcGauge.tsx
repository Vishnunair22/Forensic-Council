"use client";

import { useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";

function useAnimatedValue(target: number, duration = 1000): number {
  const [display, setDisplay] = useState(0);
  const prevTarget = useRef(0);
  const raf = useRef<number>(0);

  useEffect(() => {
    const start = prevTarget.current;
    const diff = target - start;
    if (diff === 0) return;
    const startTime = performance.now();

    function tick(now: number) {
      const t = Math.min((now - startTime) / duration, 1);
      const eased = 1 - Math.pow(1 - t, 4); // Quartic ease out
      setDisplay(Math.round(start + diff * eased));
      if (t < 1) {
        raf.current = requestAnimationFrame(tick);
      } else {
        prevTarget.current = target;
      }
    }
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [target, duration]);

  return display;
}

interface ArcGaugeProps {
  value: number;
  size?: number;
  strokeWidth?: number;
  color?: string;
  label?: string;
  sublabel?: string;
}

/**
 * Horizon ArcGauge: A high-fidelity digital forensic dial.
 */
export function ArcGauge({
  value,
  size = 140,
  strokeWidth = 3,
  color = "#00FFFF",
  label,
  sublabel,
}: ArcGaugeProps) {
  const clampedValue = Math.max(0, Math.min(100, value));
  const animatedValue = useAnimatedValue(clampedValue);
  const radius = (size - strokeWidth * 6) / 2;
  const cx = size / 2;
  const cy = size / 2;

  const startAngle = Math.PI;
  const endAngle = 0;

  function polarToXY(angle: number, r: number) {
    return {
      x: cx + r * Math.cos(angle),
      y: cy + r * Math.sin(angle),
    };
  }

  const trackStart = polarToXY(startAngle, radius);
  const trackEnd = polarToXY(endAngle, radius);
  const trackPath = `M ${trackStart.x} ${trackStart.y} A ${radius} ${radius} 0 0 1 ${trackEnd.x} ${trackEnd.y}`;

  const fillAngle = startAngle - (clampedValue / 100) * Math.PI;
  const fillEnd = polarToXY(fillAngle, radius);
  const largeArc = clampedValue > 50 ? 1 : 0;
  const fillPath = `M ${trackStart.x} ${trackStart.y} A ${radius} ${radius} 0 ${largeArc} 1 ${fillEnd.x} ${fillEnd.y}`;

  return (
    <div
      className="flex flex-col items-center gap-1"
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={clampedValue}
    >
      <div className="relative" style={{ width: size, height: size / 2 + 10 }}>
        <svg
          width={size}
          height={size / 2 + 10}
          viewBox={`0 0 ${size} ${size}`}
          aria-hidden="true"
          className="overflow-visible"
        >
          {/* Outer Decorative Dashed Ring */}
          <motion.circle
            cx={cx}
            cy={cy}
            r={radius + 12}
            fill="none"
            stroke="rgba(167,255,210,0.1)"
            strokeWidth="1"
            strokeDasharray="4 8"
            animate={{ rotate: 360 }}
            transition={{ duration: 40, repeat: Infinity, ease: "linear" }}
            style={{ originX: "50%", originY: "50%" }}
          />

          {/* Track */}
          <path
            d={trackPath}
            fill="none"
            stroke="rgba(255,255,255,0.05)"
            strokeWidth={strokeWidth}
            strokeLinecap="round"
          />

          {/* Fill Arc */}
          {clampedValue > 0 && (
            <motion.path
              initial={{ pathLength: 0 }}
              animate={{ pathLength: 1 }}
              d={fillPath}
              fill="none"
              stroke={color === "#00FFFF" ? "var(--color-success-light)" : color}
              strokeWidth={strokeWidth + 2}
              strokeLinecap="round"
              style={{
                filter: `drop-shadow(0 0 12px ${color === "#00FFFF" ? "rgba(167,255,210,0.4)" : color + "88"})`,
              }}
            />
          )}


          {/* Dial Markers */}
          {[0, 0.25, 0.5, 0.75, 1].map((pos) => {
            const angle = Math.PI - pos * Math.PI;
            const p1 = polarToXY(angle, radius - 6);
            const p2 = polarToXY(angle, radius - 2);
            return (
              <line
                key={pos}
                x1={p1.x}
                y1={p1.y}
                x2={p2.x}
                y2={p2.y}
                stroke="rgba(255,255,255,0.2)"
                strokeWidth="1"
              />
            );
          })}
        </svg>

        {/* Central Counter */}
        <div className="absolute bottom-2 left-0 right-0 flex flex-col items-center">
          <span className="text-3xl font-mono font-bold tracking-tighter tabular-nums text-white" style={{ color: clampedValue > 0 ? color : 'rgba(255,255,255,0.2)' }}>
            {animatedValue}<span className="text-sm opacity-40 ml-0.5">%</span>
          </span>
        </div>
      </div>

      <div className="mt-2 flex flex-col items-center">
        {label && (
          <span className="text-[10px] font-mono font-bold text-white/30 uppercase tracking-[0.2em]">
            {label}
          </span>
        )}
        {sublabel && (
          <span className="text-[9px] font-mono text-white/20 uppercase tracking-widest mt-0.5">
            {sublabel}
          </span>
        )}
      </div>
    </div>
  );
}
