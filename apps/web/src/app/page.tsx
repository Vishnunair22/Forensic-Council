"use client";

import { motion } from "framer-motion";
import { HowWorksSection } from "@/components/ui/HowWorksSection";
import { AgentsSection } from "@/components/ui/AgentsSection";
import { HeroAuthActions } from "@/components/ui/HeroAuthActions";

export default function Home() {
  return (
    <div className="relative bg-transparent text-foreground min-h-screen selection:bg-primary/20 selection:text-white">

      {/* --- Horizon Hero Section --- */}
      <motion.div
        className="relative w-full h-screen flex flex-col items-center justify-center z-10 overflow-hidden"
      >
        {/* Volumetric Horizon Glow */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-[60%] w-[800px] h-[500px] bg-primary/5 blur-[150px] rounded-[100%] pointer-events-none z-0" />

        <div className="flex flex-col items-center justify-center text-center px-6 relative z-10 pointer-events-auto gap-10">
          
          <motion.div
             initial={{ opacity: 0, scale: 0.98, y: 30, filter: "blur(10px)" }}
             animate={{ opacity: 1, scale: 1, y: 0, filter: "blur(0px)" }}
             transition={{ duration: 1.5, ease: [0.16, 1, 0.3, 1] }}
             className="flex flex-col items-center relative"
          >
            <h1
              className="text-5xl md:text-7xl lg:text-[6rem] font-bold max-w-6xl tracking-tight leading-[1.1] flex flex-col items-center"
            >
              <span className="block text-white/95 pb-2">
                Multi-Agent Forensic
              </span>
              <span className="block text-primary drop-shadow-[0_0_40px_rgba(0,255,255,0.25)]">
                Evidence Analysis System
              </span>
            </h1>
          </motion.div>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4, duration: 1.2 }}
            className="text-base md:text-lg font-medium text-white/60 max-w-3xl mx-auto leading-relaxed tracking-wide"
          >
            Forensic Council is a Multi-Agent AI-based application, that uses multiple customized agents to analyze digital forensic evidence to create a cohesive and effective report.
          </motion.p>

          <motion.div 
            initial={{ opacity: 0, y: 30 }} 
            animate={{ opacity: 1, y: 0 }} 
            transition={{ delay: 0.7, duration: 1 }} 
            className="flex flex-col items-center"
          >
            <HeroAuthActions />
          </motion.div>
        </div>

        <motion.div 
          initial={{ opacity: 0 }}
          animate={{ opacity: [0, 0.6, 0], y: [0, 10, 0] }}
          transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
          className="absolute bottom-12 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2"
        >
          <span className="text-[10px] font-mono uppercase tracking-[0.3em] text-primary/40">Scroll To Inspect</span>
          <div className="w-[1px] h-16 bg-gradient-to-b from-primary/60 to-transparent" />
        </motion.div>
      </motion.div>

      {/* --- Scrolling Content (The Glide Effect) ---  */}
      <div className="relative z-20 w-full px-4 pb-32">
        <motion.div
          initial={{ opacity: 0, y: 200 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ margin: "-100px", once: true }}
          transition={{ duration: 1.5, ease: [0.16, 1, 0.3, 1] }}
          className="horizon-glass min-h-screen rounded-[3rem] shadow-[0_60px_150px_rgba(0,0,0,0.9)] overflow-hidden border-primary/10"
        >
          {/* Decorative Handle */}
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-24 h-1 bg-primary/20 rounded-full mt-6" />
          
          <div className="pt-12">
            <HowWorksSection />
            <AgentsSection />
          </div>
        </motion.div>
      </div>
    </div>
  );
}
