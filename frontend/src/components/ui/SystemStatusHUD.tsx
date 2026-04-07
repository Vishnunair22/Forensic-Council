"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { AGENTS } from "@/lib/constants";
import { Activity, Shield, Cpu, Binary } from "lucide-react";

export function SystemStatusHUD() {
  const [uptime, setUptime] = useState("00:00:00");
  const [load, setLoad] = useState(12);

  useEffect(() => {
    const start = Date.now();
    const interval = setInterval(() => {
      const diff = Date.now() - start;
      const hours = Math.floor(diff / 3600000).toString().padStart(2, "0");
      const minutes = Math.floor((diff % 3600000) / 60000).toString().padStart(2, "0");
      const seconds = Math.floor((diff % 60000) / 1000).toString().padStart(2, "0");
      setUptime(`${hours}:${minutes}:${seconds}`);
      setLoad(Math.floor(10 + Math.random() * 5));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="absolute inset-0 z-10 pointer-events-none p-6 font-mono text-[7px] uppercase tracking-[.3em] font-medium text-cyan-500/30">
      {/* HUD Frame - Discrete Corner Markers */}
      <div className="absolute top-24 left-8 w-4 h-4 border-t border-l border-cyan-500/20" />
      <div className="absolute top-24 right-8 w-4 h-4 border-t border-r border-cyan-500/20" />
      <div className="absolute bottom-24 left-8 w-4 h-4 border-b border-l border-cyan-500/20" />
      <div className="absolute bottom-24 right-8 w-4 h-4 border-b border-r border-cyan-500/20" />

      {/* Mid Left: System Metrics */}
      <div className="absolute top-1/2 -translate-y-1/2 left-10 flex flex-col gap-8 hud-glow">
        <div className="flex flex-col gap-3">
           <div className="flex items-center gap-3 opacity-60">
              <Activity className="w-2.5 h-2.5 animate-pulse text-cyan-400" />
              <span className="text-white/40">Core Status // Online</span>
           </div>
           <div className="w-20 h-[1px] bg-cyan-500/10" />
           <div className="flex flex-col gap-1">
              <span className="text-white/10 text-[5px]">UPTIME: {uptime}</span>
              <span className="text-white/10 text-[5px]">HASH_RATE: 4.2 GH/s</span>
           </div>
        </div>

        <div className="flex flex-col gap-3">
           <div className="flex items-center gap-3 opacity-60">
              <Cpu className="w-2.5 h-2.5 text-cyan-400" />
              <span className="text-white/40">Neural Load // {load}%</span>
           </div>
           <div className="w-20 bg-white/5 h-[1px] overflow-hidden">
              <motion.div 
                animate={{ width: `${load}%` }}
                className="h-full bg-cyan-500 shadow-[0_0_5px_rgba(34,211,238,0.5)]" 
              />
           </div>
        </div>
      </div>

      {/* Mid Right: Agent Manifest */}
      <div className="absolute top-1/2 -translate-y-1/2 right-10 flex flex-col items-end gap-6 text-right hud-glow">
        <div className="flex items-center gap-3 text-white/20">
            <Binary className="w-2.5 h-2.5 text-cyan-400" />
            <span>Agent Collective // Valid</span>
        </div>
        <div className="flex flex-col gap-2">
          {AGENTS.map((agent, i) => (
            <div key={agent.id} className="flex items-center gap-3 justify-end group">
                <span className="text-[5px] text-white/5 group-hover:text-cyan-500/40 transition-colors uppercase tracking-widest">{agent.name}</span>
                <motion.div
                  initial={{ scaleX: 0 }}
                  animate={{ scaleX: 1 }}
                  transition={{ delay: i * 0.05, duration: 0.5 }}
                  className="w-4 h-[1px] bg-cyan-500/20 origin-right group-hover:bg-cyan-500 group-hover:shadow-[0_0_5px_rgba(34,211,238,0.5)] transition-all"
                />
            </div>
          ))}
        </div>
        <div className="mt-2 text-[5px] text-white/5 tracking-[.5em]">ALL UNITS STANDBY</div>
      </div>

      {/* Bottom Sidebars: Registry Metadata */}
      <div className="absolute bottom-32 left-10 rotate-[-90deg] origin-left opacity-10 text-[6px] flex items-center gap-6 font-light">
        <span>ESTABLISHING CHAIN_OF_CUSTODY</span>
        <div className="w-10 h-[1px] bg-cyan-500/40" />
        <span>V2.0.26_STABLE</span>
      </div>

      <div className="absolute bottom-10 right-10 flex items-center gap-5 opacity-40">
         <div className="flex flex-col items-end gap-1">
            <span className="text-white/10 text-[5px]">SECURITY_PROTOCOL:</span>
            <span className="text-cyan-400 tracking-widest">ECDSA_P256</span>
         </div>
         <div className="w-8 h-8 rounded-full border border-cyan-500/10 flex items-center justify-center p-1.5 glass-card-refined">
            <Shield className="w-full h-full text-cyan-400" />
         </div>
      </div>
    </div>
  );
}
