"use client";

import React from "react";
import { motion } from "framer-motion";
import { Activity, ShieldAlert, Zap } from "lucide-react";

interface VerdictGaugeProps {
  confPct: number;
  manipPct: number;
  errPct: number;
  discordPct: number;
  calibrationStatus?: string; // "TRAINED" | "UNCALIBRATED"
}

export function VerdictGauge({
  confPct,
  manipPct,
  errPct,
  discordPct,
  calibrationStatus,
}: VerdictGaugeProps) {
  const isUncalibrated = calibrationStatus !== "TRAINED";
  return (
    <section className="overflow-hidden border border-border-muted bg-surface-1 rounded-2xl">
      <div className="grid grid-cols-1 md:grid-cols-4 divide-y md:divide-y-0 md:divide-x divide-border-muted">
        
        {/* Consensus Confidence */}
        <div className="p-8 flex flex-col items-center justify-center text-center">
          <span className="text-[10px] font-mono font-bold text-white/50 tracking-[0.2em] mb-4 uppercase">Consensus Confidence</span>
          
          <div className="text-6xl font-black text-white tracking-tighter">
            {confPct}%
          </div>

          {isUncalibrated && (
            <span className="text-[8px] font-mono text-warning bg-surface-2 border border-border-muted px-2 py-1 mt-6 uppercase tracking-widest">
              Uncalibrated
            </span>
          )}
        </div>

        {/* Integrity Risk */}
        <StatCard
          label="Integrity Risk"
          value={manipPct}
          unit="%"
          subtext="Manipulation Prob."
          icon={ShieldAlert}
          color={manipPct > 50 ? "var(--color-danger)" : "var(--color-success-light)"}
        />

        {/* System Noise */}
        <StatCard
          label="System Noise"
          value={errPct}
          unit="%"
          subtext="Error Variance"
          icon={Zap}
          color={errPct > 20 ? "var(--color-warning)" : "var(--color-success-light)"}
        />

        {/* Agent Spread */}
        <StatCard
          label="Agent Spread"
          value={discordPct}
          unit="%"
          subtext="Neural Discord"
          icon={Activity}
          color="var(--color-success-light)"
        />

      </div>
    </section>
  );
}

interface StatCardProps {
  label: string;
  value: number;
  unit: string;
  subtext: string;
  icon: React.ElementType;
  color: string;
}

function StatCard({ label, value, unit, subtext, icon: Icon, color }: StatCardProps) {
  return (
    <div className="p-8 flex flex-col items-center justify-center text-center group">
      <div className="flex items-center gap-3 mb-6">
        <Icon className="w-3.5 h-3.5 text-white/10 group-hover:text-white/30 transition-colors" />
        <span className="text-[10px] font-mono font-bold text-white/20 tracking-[0.2em]">{label}</span>
      </div>
      
      <div className="text-4xl font-mono font-bold text-white mb-4 tracking-tighter" style={{ color }}>
        {value}{unit}
      </div>

      <div className="w-full max-w-[120px] h-1 bg-white/5 rounded-full overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${value}%` }}
          className="h-full"
          style={{ backgroundColor: color }}
        />
      </div>
      
      <span className="text-[9px] font-mono text-white/10 mt-4 tracking-widest">{subtext}</span>
    </div>
  );
}
