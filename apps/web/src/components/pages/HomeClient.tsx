"use client";

import dynamic from "next/dynamic";
import { HeroAuthActions } from "@/components/ui/HeroAuthActions";
import { motion, useReducedMotion, type Variants } from "framer-motion";

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
          className="flex flex-col items-start w-full max-w-7xl mx-auto z-10"
        >
          {/* Eyebrow */}
          <motion.div variants={itemVariants} className="flex items-center gap-3 mb-8">
            <span className="text-xs font-mono font-semibold tracking-[0.2em] text-slate-500 uppercase">
              [ System Overview ]
            </span>
          </motion.div>

          {/* Headline */}
          <div className="space-y-6 mb-12 max-w-4xl">
            <motion.h1
              variants={itemVariants}
              className="text-5xl sm:text-6xl md:text-[80px] font-extrabold leading-[1.02] text-white"
              style={{ letterSpacing: "-0.03em" }}
            >
              Multi-Agent Forensic
              <br />
              Evidence Analysis
            </motion.h1>

            <motion.p
              variants={itemVariants}
              className="text-lg md:text-xl text-slate-400 font-medium leading-relaxed max-w-2xl"
            >
              Forensic Council deploys specialized AI agents to analyze digital evidence,
              synthesizing cohesive, cryptographically-signed reports with chain-of-custody integrity.
            </motion.p>
          </div>

          {/* CTA */}
          <motion.div variants={itemVariants} className="mt-4">
            <HeroAuthActions />
          </motion.div>

        </motion.div>

        {/* Bottom fade */}
        <div
          className="absolute inset-x-0 bottom-0 h-24 pointer-events-none"
          style={{ background: "linear-gradient(to bottom, transparent, var(--color-background))" }}
        />
      </section>

      {/* ── Content sections ── */}
      <section className="relative w-full px-4 sm:px-6 pb-32 max-w-7xl mx-auto space-y-32">
        <div>
          <HowWorksSection />
        </div>

        <div>
          <AgentsSection />
        </div>
      </section>

    </div>
  );
}