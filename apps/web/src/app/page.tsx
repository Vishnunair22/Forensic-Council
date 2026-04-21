"use client";

import { motion } from "framer-motion";
import { HowWorksSection } from "@/components/ui/HowWorksSection";
import { AgentsSection } from "@/components/ui/AgentsSection";
import { HeroAuthActions } from "@/components/ui/HeroAuthActions";

export default function Home() {
  return (
    <div className="relative bg-black text-white min-h-screen">
      {/* --- Normal Hero Section --- */}
      <motion.div
        className="relative w-full h-screen flex flex-col items-center justify-center z-10"
      >
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px]"></div>
        <div className="absolute left-0 right-0 top-0 -z-10 m-auto h-[310px] w-[310px] rounded-full bg-cyan-500 opacity-20 blur-[100px]"></div>

        <div className="flex flex-col items-center justify-center text-center px-6 relative z-10 pointer-events-auto gap-8">
          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-4xl md:text-7xl font-bold max-w-5xl tracking-tighter text-white font-heading"
          >
            Multi-Agent Forensic <br/>
            <span className="text-cyan-400">Evidence Analysis System</span>
          </motion.h1>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2 }}
            className="text-lg md:text-xl leading-relaxed text-neutral-400 max-w-2xl mx-auto"
          >
            Forensic Council uses coordinated AI agents to analyze digital evidence, cross-check findings, and produce a cohesive forensic report.
          </motion.p>
          <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.4 }} className="flex flex-col items-center mt-2">
            <HeroAuthActions />
          </motion.div>
        </div>


      </motion.div>

      {/* --- Scrolling Content Section ---  */}
      <div className="relative z-10 w-full">
        <motion.div
          className="bg-black min-h-screen rounded-t-[3rem] border-t border-white/10 shadow-[0_-20px_60px_rgba(0,0,0,0.9)]"
        >
          <HowWorksSection />
          <AgentsSection />
        </motion.div>
      </div>


    </div>
  );
}
