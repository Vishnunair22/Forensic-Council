"use client";

import { motion } from "framer-motion";

export function GlobalFooter() {
  return (
    <footer className="w-full py-12 px-8 relative z-50 border-t border-white/[0.05] bg-[#06090F]/80 backdrop-blur-3xl">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-6">
        <div className="flex flex-col items-center md:items-start gap-2">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-cyan-400" />
            <span className="text-[10px] font-black uppercase tracking-[0.3em] font-heading text-white">
              Forensic Council
            </span>
          </div>
          <p className="text-[9px] font-mono font-bold text-white/20 uppercase tracking-[0.1em]">
            Multi-Agent Forensic Intelligence Interface
          </p>
        </div>
        
        <div className="max-w-md text-center md:text-right">
          <p className="text-[10px] font-medium text-white/30 tracking-tight leading-relaxed">
            Forensic Council uses sophisticated ML agents to analyze evidence. 
            All findings are calibrated for high-precision forensic review. 
            Verification by human investigator recommended.
          </p>
        </div>
      </div>
      
      <div className="max-w-7xl mx-auto mt-8 pt-8 border-t border-white/[0.03] flex justify-center">
        <span className="text-[8px] font-mono font-black text-white/10 uppercase tracking-[0.5em]">
          &copy; 2026 FORENSIC COUNCIL · CRYPTOGRAPHICALLY SIGNED REPORTS
        </span>
      </div>
    </footer>
  );
}
