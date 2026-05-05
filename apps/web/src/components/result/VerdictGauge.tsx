"use client";

import React from "react";
import { motion } from "framer-motion";
import { ArcGauge } from "./ArcGauge";
import { Activity, ShieldAlert, Zap } from "lucide-react";

interface VerdictGaugeProps {
  confPct: number;
  manipPct: number;
  errPct: number;
  discordPct: number;
}

export function VerdictGauge({
  confPct,
  manipPct,
  errPct,
  discordPct,
}: VerdictGaugeProps) {
  return (
    <section className="bg-[#070A12] border border-white/8 rounded-2xl shadow-[0_4px_24px_rgba(0,0,0,0.5),0_1px_0_rgba(255,255,255,0.04)_inset] overflow-hidden">
      <div className="grid grid-cols-1 md:grid-cols-4 divide-y md:divide-y-0 md:divide-x divide-white/5">
        
        {/* Consensus Confidence (ArcGauge) */}
        <div className="p-8 flex flex-col items-center justify-center text-center">
          <div className="w-32 h-32 flex items-center justify-center">
            <ArcGauge value={confPct} label="" sublabel="" color="#A7FFD2" />
          </div>
          <span className="text-[10px] font-mono font-bold text-white/20 uppercase tracking-[0.2em] mt-4">Consensus_Confidence</span>
          <div className="text-xl font-mono font-bold text-white mt-1">{confPct}%</div>
        </div>

        {/* Integrity Risk */}
        <StatCard 
          label="Integrity_Risk" 
          value={manipPct} 
          unit="%" 
          subtext="Manipulation Prob." 
          icon={ShieldAlert}
          color={manipPct > 50 ? "#F43F5E" : "#A7FFD2"}
        />

        {/* System Noise */}
        <StatCard 
          label="System_Noise" 
          value={errPct} 
          unit="%" 
          subtext="Error Variance" 
          icon={Zap}
          color={errPct > 20 ? "#F59E0B" : "#A7FFD2"}
        />

        {/* Agent Spread */}
        <StatCard 
          label="Agent_Spread" 
          value={discordPct} 
          unit="%" 
          subtext="Neural Discord" 
          icon={Activity}
          color="#A7FFD2"
        />

      </div>
    </section>
  );
}

function StatCard({ label, value, unit, subtext, icon: Icon, color }: any) {
  return (
    <div className="p-8 flex flex-col items-center justify-center text-center group">
      <div className="flex items-center gap-3 mb-6">
        <Icon className="w-3.5 h-3.5 text-white/10 group-hover:text-white/30 transition-colors" />
        <span className="text-[10px] font-mono font-bold text-white/20 uppercase tracking-[0.2em]">{label}</span>
      </div>
      
      <div className="text-4xl font-mono font-bold text-white mb-4 tracking-tighter" style={{ color }}>
        {value}{unit}
      </div>

      <div className="w-full max-w-[120px] h-1 bg-white/5 rounded-full overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${value}%` }}
          className="h-full"
          style={{ 
            backgroundColor: color, 
            boxShadow: `0 0 15px ${color}80` 
          }}
        />
      </div>
      
      <span className="text-[9px] font-mono text-white/10 mt-4 uppercase tracking-widest">{subtext}</span>
    </div>
  );
}
