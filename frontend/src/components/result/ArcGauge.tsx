"use client";

interface ArcGaugeProps {
  /** Value 0–100 */
  value: number;
  /** Diameter in pixels */
  size?: number;
  strokeWidth?: number;
  /** Tailwind / CSS color for the filled arc */
  color?: string;
  label?: string;
  sublabel?: string;
}

/**
 * SVG half-arc gauge (180° sweep).
 * Fully accessible — value + labels are in visible text so screen readers
 * never need to parse the SVG path.
 */
export function ArcGauge({
  value,
  size = 120,
  strokeWidth = 10,
  color = "#22d3ee",
  label,
  sublabel,
}: ArcGaugeProps) {
  const clampedValue = Math.max(0, Math.min(100, value));
  const radius = (size - strokeWidth) / 2;
  const cx = size / 2;
  const cy = size / 2;

  // Half-circle: starts at 180° (left) → sweeps to 0° (right)
  const startAngle = Math.PI; // 180°
  const endAngle = 0;         // 0°

  function polarToXY(angle: number, r: number) {
    return {
      x: cx + r * Math.cos(angle),
      y: cy + r * Math.sin(angle),
    };
  }

  const trackStart = polarToXY(startAngle, radius);
  const trackEnd = polarToXY(endAngle, radius);
  const trackPath = `M ${trackStart.x} ${trackStart.y} A ${radius} ${radius} 0 0 1 ${trackEnd.x} ${trackEnd.y}`;

  // Fill arc: sweeps proportional to value (0 = nothing, 100 = full half)
  const fillAngle = startAngle - (clampedValue / 100) * Math.PI;
  const fillEnd = polarToXY(fillAngle, radius);
  const largeArc = clampedValue > 50 ? 1 : 0;
  const fillPath = `M ${trackStart.x} ${trackStart.y} A ${radius} ${radius} 0 ${largeArc} 1 ${fillEnd.x} ${fillEnd.y}`;

  const viewBox = `0 0 ${size} ${size}`;

  return (
    <div
      className="flex flex-col items-center gap-1"
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={clampedValue}
      aria-label={label ? `${label}: ${clampedValue}%` : `${clampedValue}%`}
    >
      <svg
        width={size}
        height={size / 2 + strokeWidth}
        viewBox={viewBox}
        aria-hidden="true"
        overflow="visible"
      >
        {/* Track */}
        <path
          d={trackPath}
          fill="none"
          stroke="rgba(255,255,255,0.08)"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
        />
        {/* Fill */}
        {clampedValue > 0 && (
          <path
            d={fillPath}
            fill="none"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            style={{
              filter: `drop-shadow(0 0 6px ${color}55)`,
              transition: "stroke-dashoffset 0.6s cubic-bezier(0.4,0,0.2,1)",
            }}
          />
        )}
      </svg>

      {/* Numeric label */}
      <span
        className="text-2xl font-black tabular-nums font-mono leading-none"
        style={{ color }}
      >
        {clampedValue}
        <span className="text-sm font-bold opacity-60">%</span>
      </span>

      {label && (
        <span className="text-[10px] font-bold uppercase tracking-widest text-white/50 text-center">
          {label}
        </span>
      )}
      {sublabel && (
        <span className="text-[9px] font-mono text-white/25 text-center">
          {sublabel}
        </span>
      )}
    </div>
  );
}
