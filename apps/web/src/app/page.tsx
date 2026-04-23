"use client";

import { motion } from "framer-motion";
import { HowWorksSection } from "@/components/ui/HowWorksSection";
import { AgentsSection } from "@/components/ui/AgentsSection";
import { HeroAuthActions } from "@/components/ui/HeroAuthActions";

export default function Home() {
  return (
    <div className="relative bg-black text-foreground min-h-screen selection:bg-primary/20 selection:text-white">

      {/* --- Normal Hero Section --- */}
      <motion.div
        className="relative w-full h-screen flex flex-col items-center justify-center z-10 overflow-hidden"
      >
        {/* NEW: Cyber Blueprint Grid (Adds subtle technical depth) */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff0a_1px,transparent_1px),linear-gradient(to_bottom,#ffffff0a_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_60%_at_50%_40%,#000_40%,transparent_100%)] pointer-events-none z-0" />

        {/* Volumetric Background Glow */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-[60%] w-[800px] h-[500px] bg-primary/5 blur-[120px] rounded-[100%] pointer-events-none z-0" />

        <div className="flex flex-col items-center justify-center text-center px-6 relative z-10 pointer-events-auto gap-8">
          <motion.div
             initial={{ opacity: 0, scale: 0.95, y: 20 }}
             animate={{ opacity: 1, scale: 1, y: 0 }}
             transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
             className="flex flex-col items-center"
          >
            {/* NEW: Gradient & Shadowed Typography */}
            <h1
              className="text-5xl md:text-7xl lg:text-[5.5rem] font-black max-w-6xl tracking-[-0.03em] leading-none flex flex-col items-center"
            >
              <span className="block text-white/95 pb-2">
                Multi-Agent Forensic
              </span>
              <span className="block text-primary drop-shadow-[0_0_40px_rgba(var(--primary),0.2)]">
                Evidence Analysis System
              </span>
            </h1>
          </motion.div>

          {/* NEW: Tighter, balanced subtext */}
          <motion.p
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3, duration: 1 }}
            className="text-base md:text-lg font-medium text-white/60 max-w-3xl mx-auto leading-relaxed tracking-wide mt-2 mb-4"
          >
            Forensic Council is a Multi-Agent AI-based application, that uses multiple customized agents to analyze digital forensic evidence to create a cohesive and effective report.
          </motion.p>

          <motion.div 
            initial={{ opacity: 0, y: 20 }} 
            animate={{ opacity: 1, y: 0 }} 
            transition={{ delay: 0.5, duration: 1 }} 
            className="flex flex-col items-center relative"
          >
            {/* NEW: Subtle ring around the action area to frame the button */}
            <div className="absolute inset-0 -m-6 border border-white/5 rounded-full opacity-50 scale-110 pointer-events-none" />
            <div className="absolute inset-0 -m-12 border border-white/[0.02] rounded-full opacity-50 scale-125 pointer-events-none" />
            
            <HeroAuthActions />
          </motion.div>
        </div>

        <motion.div 
          initial={{ opacity: 0 }}
          animate={{ opacity: [0, 0.5, 0], y: [0, 15, 0] }}
          transition={{ duration: 2.5, repeat: Infinity, ease: "easeInOut" }}
          className="absolute bottom-12 left-1/2 -translate-x-1/2 flex flex-col items-center gap-1"
        >
          <span className="text-[11px] font-mono font-semibold text-white/40 tracking-wide">Scroll To Inspect</span>
          <div className="w-[2px] h-12 mt-2 bg-gradient-to-b from-primary/50 to-transparent rounded-full" />
        </motion.div>
      </motion.div>

      {/* --- Scrolling Content Section ---  */}
      <div className="relative z-20 w-full px-4 pb-32">
        <motion.div
          initial={{ opacity: 0, y: 100 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ margin: "-100px" }}
          transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
          className="bg-white/[0.05] backdrop-blur-xl border border-white/10 min-h-screen rounded-[4rem] shadow-[0_40px_120px_rgba(0,0,0,0.8)] overflow-hidden"
        >
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-32 h-1.5 bg-white/5 rounded-full mt-8" />
          <HowWorksSection />
          <AgentsSection />
        </motion.div>
      </div>
    </div>
  );
}
