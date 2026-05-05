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
      <section id="hero" className="relative w-full min-h-screen flex flex-col items-center justify-center pt-32 pb-20 px-6">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="flex flex-col items-center text-center max-w-5xl mx-auto gap-8"
        >
          <div className="space-y-4">

            <h1 className="text-5xl md:text-7xl font-extrabold tracking-tighter leading-[0.9] text-white">
              Multi-Agent Forensic <br />
              <span className="text-white/90">Evidence Analysis System</span>
            </h1>

            <p className="text-lg md:text-xl text-white/70 max-w-3xl mx-auto font-medium leading-relaxed">
              <span className="text-primary/60 font-bold uppercase tracking-[0.3em] text-[10px] block mb-4">System_Overview</span>
              Forensic Council is a Multi-Agent AI application that utilizes specialized agents to analyze digital forensic evidence and synthesize cohesive, authoritative reports.
            </p>



          </div>

          <div className="flex flex-col items-center mt-4">
            <HeroAuthActions />
          </div>

          {/* Decorative Elements */}
          <div className="grid grid-cols-3 gap-8 mt-12 opacity-40">
            <div className="flex flex-col items-center gap-2">
              <Cpu className="w-5 h-5 text-primary" />
              <span className="text-[10px] uppercase tracking-tighter font-mono">Neural Processing</span>
            </div>
            <div className="flex flex-col items-center gap-2">
              <Scale className="w-5 h-5 text-primary" />
              <span className="text-[10px] uppercase tracking-tighter font-mono">Arbiter Protocol</span>
            </div>
            <div className="flex flex-col items-center gap-2">
              <Shield className="w-5 h-5 text-primary" />
              <span className="text-[10px] uppercase tracking-tighter font-mono">Chain of Custody</span>
            </div>
          </div>
        </motion.div>
      </section>

      {/* --- Content Section ---  */}
      <section className="relative w-full px-6 pb-32 max-w-7xl mx-auto space-y-20">
        <GlassPanel className="relative overflow-hidden group">
          <div className="absolute top-0 right-0 p-8 opacity-10 group-hover:opacity-20 transition-opacity">
            <Cpu className="w-32 h-32 text-primary" />
          </div>
          <HowWorksSection />
        </GlassPanel>

        <GlassPanel className="relative overflow-hidden group">
          <div className="absolute top-0 left-0 p-8 opacity-10 group-hover:opacity-20 transition-opacity">
            <Scale className="w-32 h-32 text-primary" />
          </div>
          <AgentsSection />
        </GlassPanel>
      </section>

    </div>
  );
}
