"use client";

import { motion } from "framer-motion";
import { HowWorksSection } from "@/components/ui/HowWorksSection";
import { AgentsSection } from "@/components/ui/AgentsSection";
import { HeroAuthActions } from "@/components/ui/HeroAuthActions";

export default function Home() {
  return (
    <div className="relative bg-black text-foreground min-h-screen selection:bg-primary/20 selection:text-white">
      {/* --- Scan Line Effect --- */}
      <div className="scan-line-overlay" />
      
      {/* --- Noise Overlay for texture --- */}
      <div className="absolute inset-0 pointer-events-none opacity-[0.03] bg-[url('https://grainy-gradients.vercel.app/noise.svg')] z-[5]" />

      {/* --- Normal Hero Section --- */}
      <motion.div
        className="relative w-full h-screen flex flex-col items-center justify-center z-10 overflow-hidden"
      >
        <div className="flex flex-col items-center justify-center text-center px-6 relative z-10 pointer-events-auto gap-12">
          <motion.div
             initial={{ opacity: 0, y: 30 }}
             animate={{ opacity: 1, y: 0 }}
             transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }}
             className="flex flex-col items-center"
          >
            <span className="text-[10px] font-mono font-bold tracking-[0.5em] text-primary/60 mb-6 uppercase">Neural Forensic Protocol v4.0</span>
            <h1
              className="text-5xl md:text-7xl font-bold max-w-7xl tracking-tighter text-white leading-[0.9] drop-shadow-[0_0_50px_rgba(0,255,65,0.1)] flex flex-col"
            >
              <span className="block">Multi Agent Forensic</span>
              <span className="text-primary text-glow-green block">Evidence Analysis System</span>
            </h1>
          </motion.div>

          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.4, duration: 1.2 }}
            className="text-lg md:text-xl font-medium text-white/70 max-w-5xl mx-auto leading-relaxed tracking-tight"
          >
            Forensic Council is a Multi Agent AI based application, that uses multiple customized agents to analyse digital forensic evidence to create a cohesive and effective report.
          </motion.p>

          <motion.div 
            initial={{ opacity: 0, y: 20 }} 
            animate={{ opacity: 1, y: 0 }} 
            transition={{ delay: 0.6, duration: 1 }} 
            className="flex flex-col items-center"
          >
            <HeroAuthActions />
          </motion.div>
        </div>

        {/* Scroll Indicator */}
        <motion.div 
          initial={{ opacity: 0 }}
          animate={{ opacity: [0, 0.4, 0], y: [0, 10, 0] }}
          transition={{ duration: 3, repeat: Infinity }}
          className="absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2"
        >
          <span className="text-[9px] font-mono font-bold text-white/20 tracking-widest uppercase">Scroll to Inspect</span>
          <div className="w-[1px] h-12 bg-gradient-to-b from-primary/20 to-transparent" />
        </motion.div>
      </motion.div>

      {/* --- Scrolling Content Section ---  */}
      <div className="relative z-20 w-full px-4 pb-32">
        <motion.div
          initial={{ opacity: 0, y: 100 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ margin: "-100px" }}
          transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
          className="glass-panel min-h-screen rounded-[4rem] shadow-[0_40px_120px_rgba(0,0,0,0.8)] overflow-hidden"
        >
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-32 h-1.5 bg-white/5 rounded-full mt-8" />
          <HowWorksSection />
          <AgentsSection />
        </motion.div>
      </div>
    </div>
  );
}
