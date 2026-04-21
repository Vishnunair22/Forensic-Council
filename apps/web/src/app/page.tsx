"use client";

import { motion } from "framer-motion";
import { HowWorksSection } from "@/components/ui/HowWorksSection";
import { AgentsSection } from "@/components/ui/AgentsSection";
import { HeroAuthActions } from "@/components/ui/HeroAuthActions";

export default function Home() {
  return (
    <div className="relative bg-background text-foreground min-h-screen">
      {/* --- Normal Hero Section --- */}
      <motion.div
        className="relative w-full h-screen flex flex-col items-center justify-center z-10 overflow-hidden"
      >
        {/* Cleaner, subtler background elements matching ARGUS reference */}
        <div className="absolute inset-0 bg-grid-small opacity-[0.15]"></div>
        <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 -z-10 h-[600px] w-[800px] rounded-full bg-primary/5 blur-[120px] pointer-events-none"></div>
        <div className="absolute right-[-10%] top-[-10%] -z-10 h-[400px] w-[400px] rounded-full bg-accent/5 blur-[100px] pointer-events-none"></div>

        <div className="flex flex-col items-center justify-center text-center px-6 relative z-10 pointer-events-auto gap-10">
          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-5xl md:text-7xl font-black max-w-5xl tracking-tighter text-white font-heading leading-[0.95] drop-shadow-[0_0_30px_rgba(255,255,255,0.1)]"
          >
            Multi-Agent Forensic <br/>
            <span className="text-primary text-glow-cyan">Evidence Analysis System</span>
          </motion.h1>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2 }}
            className="text-lg md:text-xl font-medium text-white/40 max-w-4xl mx-auto leading-relaxed tracking-tight"
          >
            Forensic Council is a multi-agent AI-based application that uses multiple customized agents to analyze digital forensic evidence to create a cohesive and effective report.
          </motion.p>
          <motion.div 
            initial={{ opacity: 0, scale: 0.9 }} 
            animate={{ opacity: 1, scale: 1 }} 
            transition={{ delay: 0.4, type: "spring", stiffness: 200, damping: 20 }} 
            className="flex flex-col items-center mt-4"
          >
            <HeroAuthActions />
          </motion.div>
        </div>
      </motion.div>

      {/* --- Scrolling Content Section ---  */}
      <div className="relative z-10 w-full">
        <motion.div
          className="bg-background min-h-screen rounded-t-[4rem] border-t border-border-subtle shadow-[0_-32px_80px_rgba(0,0,0,0.9)]"
        >
          <HowWorksSection />
          <AgentsSection />
        </motion.div>
      </div>


    </div>
  );
}
