"use client";

import dynamic from "next/dynamic";
import { GlassPanel } from "@/components/ui/GlassPanel";
import { HeroAuthActions } from "@/components/ui/HeroAuthActions";
import { motion } from "framer-motion";
import { Shield, Scale, Cpu } from "lucide-react";

const HowWorksSection = dynamic(
  () => import("@/components/ui/HowWorksSection").then((mod) => mod.HowWorksSection),
  { loading: () => <div className="min-h-56" /> },
);
const AgentsSection = dynamic(
  () => import("@/components/ui/AgentsSection").then((mod) => mod.AgentsSection),
  { loading: () => <div className="min-h-56" /> },
);

export default function Home() {
  return (
    <div className="relative min-h-screen selection:bg-primary/30 selection:text-primary-foreground">

      {/* --- Hero Section --- */}
      <section id="hero" className="relative w-full min-h-screen flex flex-col items-center justify-center pt-24 pb-20 px-6">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="flex flex-col items-center text-center max-w-5xl mx-auto gap-8"
        >
          <div className="space-y-4">

            <h1 className="text-5xl md:text-7xl font-extrabold tracking-tighter leading-[0.95] text-white">
              Multi-Agent Forensic <br />
              <span className="text-white/90">Evidence Analysis System</span>
            </h1>

            <p className="text-[11px] font-bold uppercase tracking-[0.3em] text-primary/60 font-mono mb-2">
              System_Overview
            </p>
            <p className="text-lg md:text-xl text-white/60 max-w-3xl mx-auto font-medium leading-relaxed">
              Forensic Council is a Multi-Agent AI application that utilizes specialized agents to analyze digital forensic evidence and synthesize cohesive, authoritative reports.
            </p>



          </div>

          <div className="flex flex-col items-center mt-2">
            <HeroAuthActions />
          </div>

          {/* Decorative Elements */}
          <div className="grid grid-cols-3 gap-8 mt-10 opacity-50">
            <div className="flex flex-col items-center gap-2">
              <Cpu className="w-5 h-5 text-primary/70" />
              <span className="text-[10px] uppercase tracking-widest font-mono text-white/40">Neural Processing</span>
            </div>
            <div className="flex flex-col items-center gap-2">
              <Scale className="w-5 h-5 text-primary/70" />
              <span className="text-[10px] uppercase tracking-widest font-mono text-white/40">Arbiter Protocol</span>
            </div>
            <div className="flex flex-col items-center gap-2">
              <Shield className="w-5 h-5 text-primary/70" />
              <span className="text-[10px] uppercase tracking-widest font-mono text-white/40">Chain of Custody</span>
            </div>
          </div>
        </motion.div>
      </section>

      {/* --- Content Section ---  */}
      <section className="relative w-full px-6 pb-24 max-w-7xl mx-auto space-y-16">
        <GlassPanel className="relative overflow-hidden group">
          <HowWorksSection />
        </GlassPanel>

        <GlassPanel className="relative overflow-hidden group">
          <AgentsSection />
        </GlassPanel>
      </section>

    </div>
  );
}
