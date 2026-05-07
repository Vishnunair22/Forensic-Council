"use client";

import dynamic from "next/dynamic";
import { useEffect } from "react";
import { GlassPanel } from "@/components/ui/GlassPanel";
import { HeroAuthActions } from "@/components/ui/HeroAuthActions";
import { motion, type Variants } from "framer-motion";
import { Shield, Scale, Cpu } from "lucide-react";
import { sessionOnlyStorage } from "@/lib/storage";

const HowWorksSection = dynamic(
  () => import("@/components/ui/HowWorksSection").then((mod) => mod.HowWorksSection),
  { loading: () => <div className="min-h-56" /> },
);
const AgentsSection = dynamic(
  () => import("@/components/ui/AgentsSection").then((mod) => mod.AgentsSection),
  { loading: () => <div className="min-h-56" /> },
);

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.12 } },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 18 },
  show: { opacity: 1, y: 0, transition: { duration: 0.65, ease: "easeOut" } },
};

export default function Home() {
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const openUploadOnce = sessionOnlyStorage.getItem("fc_open_upload_once");

    if (params.get("upload") !== "1" && openUploadOnce !== "1") {
      sessionOnlyStorage.removeItem("forensic_auto_start");
      sessionOnlyStorage.removeItem("fc_show_loading");
      window.sessionStorage.removeItem("forensic_auto_start");
      window.sessionStorage.removeItem("fc_show_loading");
    }
  }, []);

  return (
    <div className="relative min-h-screen selection:bg-primary/30 selection:text-primary-foreground">

      {/* --- Hero Section --- */}
      <section id="hero" className="relative w-full min-h-[92vh] flex flex-col items-center justify-center pt-28 pb-16 px-5 sm:px-6">
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="show"
          className="flex flex-col items-center text-center max-w-5xl mx-auto gap-8 z-10"
        >
          <div className="space-y-6">

            <motion.h1 variants={itemVariants} className="text-4xl sm:text-5xl md:text-7xl font-extrabold tracking-tight leading-[1.02] text-white text-glow">
              Multi-Agent Forensic <br />
              <span className="text-hero-gradient">Evidence Analysis System</span>
            </motion.h1>

            <motion.p variants={itemVariants} className="text-xs font-bold uppercase tracking-[0.24em] sm:tracking-[0.32em] text-primary-soft font-mono mb-2">
              System_Overview
            </motion.p>
            <motion.p variants={itemVariants} className="text-base md:text-xl text-slate-200/80 max-w-2xl mx-auto font-medium leading-relaxed">
              Forensic Council is a Multi-Agent AI application that utilizes specialized agents to analyze digital forensic evidence and synthesize cohesive, authoritative reports.
            </motion.p>

          </div>

          <motion.div variants={itemVariants} className="flex flex-col items-center mt-2">
            <HeroAuthActions />
          </motion.div>

          {/* Decorative Elements */}
          <motion.div variants={itemVariants} className="flex flex-wrap items-center justify-center gap-4 sm:gap-6 mt-8 text-slate-300/75">
            <div className="flex items-center gap-2">
              <Cpu className="w-4 h-4 text-primary-soft" />
              <span className="text-xs uppercase tracking-widest font-mono">Neural Processing</span>
            </div>
            <span className="hidden sm:block w-1 h-1 rounded-full bg-white/25"></span>
            <div className="flex items-center gap-2">
              <Scale className="w-4 h-4 text-primary-soft" />
              <span className="text-xs uppercase tracking-widest font-mono">Arbiter Protocol</span>
            </div>
            <span className="hidden sm:block w-1 h-1 rounded-full bg-white/25"></span>
            <div className="flex items-center gap-2">
              <Shield className="w-4 h-4 text-primary-soft" />
              <span className="text-xs uppercase tracking-widest font-mono">Chain of Custody</span>
            </div>
          </motion.div>
        </motion.div>
      </section>

      {/* --- Content Section ---  */}
      <section className="relative w-full px-6 pb-24 max-w-7xl mx-auto space-y-16">
        <GlassPanel className="relative overflow-hidden group no-hover-lift">
          <HowWorksSection />
        </GlassPanel>

        <GlassPanel className="relative overflow-hidden group no-hover-lift">
          <AgentsSection />
        </GlassPanel>
      </section>

    </div>
  );
}
