"use client";

import dynamic from "next/dynamic";
import { GlassPanel } from "@/components/ui/GlassPanel";
import { HeroAuthActions } from "@/components/ui/HeroAuthActions";
import { motion, useReducedMotion, type Variants } from "framer-motion";
import { Shield, Scale, Cpu } from "lucide-react";

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
  show: { opacity: 1, transition: { staggerChildren: 0.10, delayChildren: 0.05 } },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 22, filter: "blur(4px)" },
  show: { opacity: 1, y: 0, filter: "blur(0px)", transition: { duration: 0.7, ease: [0.16, 1, 0.3, 1] } },
};

export function HomeClient() {
  const prefersReducedMotion = useReducedMotion();
  return (
    <div className="relative min-h-screen">

      {/* ── Hero ── */}
      <section id="hero" className="relative w-full min-h-[90vh] flex flex-col items-center justify-center pt-32 pb-20 px-5 sm:px-6">
        <motion.div
          variants={prefersReducedMotion ? undefined : containerVariants}
          initial={prefersReducedMotion ? false : "hidden"}
          animate={prefersReducedMotion ? false : "show"}
          className="flex flex-col items-center text-center max-w-5xl mx-auto gap-10 z-10"
        >
          {/* Eyebrow */}
          <motion.div variants={itemVariants} className="flex items-center gap-3">
            <div
              className="h-px w-8 opacity-40"
              style={{ background: "linear-gradient(90deg, transparent, rgba(79,142,247,0.8))" }}
            />
            <span className="text-[10px] font-mono font-bold tracking-[0.3em] text-primary/60 uppercase">
              System_Overview
            </span>
            <div
              className="h-px w-8 opacity-40"
              style={{ background: "linear-gradient(90deg, rgba(79,142,247,0.8), transparent)" }}
            />
          </motion.div>

          {/* Headline */}
          <div className="space-y-4">
            <motion.h1
              variants={itemVariants}
              className="text-4xl sm:text-5xl md:text-[68px] font-extrabold leading-[1.04] text-white text-glow"
              style={{ letterSpacing: "-0.03em" }}
            >
              Multi-Agent Forensic
              <br />
              <span className="text-hero-gradient">Evidence Analysis</span>
            </motion.h1>

            <motion.p
              variants={itemVariants}
              className="text-base md:text-lg text-slate-200/65 max-w-2xl mx-auto font-medium leading-relaxed"
            >
              Forensic Council deploys specialized AI agents to analyze digital evidence,
              synthesizing cohesive, cryptographically-signed reports with chain-of-custody integrity.
            </motion.p>
          </div>

          {/* CTA */}
          <motion.div variants={itemVariants}>
            <HeroAuthActions />
          </motion.div>

          {/* Metadata strip */}
          <motion.div
            variants={itemVariants}
            className="flex flex-wrap items-center justify-center gap-5 sm:gap-7"
          >
            {[
              { icon: Cpu, label: "Neural Processing" },
              { icon: Scale, label: "Arbiter Protocol" },
              { icon: Shield, label: "Chain of Custody" },
            ].map(({ icon: Icon, label }, i) => (
              <div key={label} className="flex items-center gap-2">
                {i > 0 && (
                  <span className="hidden sm:block w-1 h-1 rounded-full bg-white/15 mr-3" />
                )}
                <Icon className="w-3.5 h-3.5" style={{ color: "rgba(165,200,255,0.55)" }} />
                <span className="text-[10px] uppercase tracking-[0.2em] font-mono text-white/35">{label}</span>
              </div>
            ))}
          </motion.div>
        </motion.div>

        {/* Bottom fade */}
        <div
          className="absolute inset-x-0 bottom-0 h-24 pointer-events-none"
          style={{ background: "linear-gradient(to bottom, transparent, var(--color-background))" }}
        />
      </section>

      {/* ── Content sections ── */}
      <section className="relative w-full px-4 sm:px-6 pb-28 max-w-7xl mx-auto space-y-14">
        <GlassPanel className="relative overflow-hidden no-hover-lift">
          <HowWorksSection />
        </GlassPanel>

        <GlassPanel className="relative overflow-hidden no-hover-lift">
          <AgentsSection />
        </GlassPanel>
      </section>

    </div>
  );
}