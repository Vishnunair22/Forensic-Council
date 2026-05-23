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
  hidden: { opacity: 0, y: 4 },
  show: { opacity: 1, y: 0, transition: { duration: 0.16, ease: "easeOut" } },
};

export function HomeClient() {
  const prefersReducedMotion = useReducedMotion();
  return (
    <div className="relative min-h-screen">

      {/* ── Hero ── */}
      <section id="hero" aria-labelledby="hero-heading" className="relative w-full min-h-[90vh] flex flex-col items-center justify-center pb-20 px-5 sm:px-6">

        <motion.div
          variants={prefersReducedMotion ? undefined : containerVariants}
          initial={prefersReducedMotion ? false : "hidden"}
          animate={prefersReducedMotion ? false : "show"}
          className="flex flex-col items-center text-center w-full max-w-4xl mx-auto z-10"
        >
          {/* Headline */}
          <div className="space-y-6 mb-12 w-full">
            <motion.h1
              id="hero-heading"
              variants={itemVariants}
              className="text-3xl lg:text-5xl xl:text-6xl font-bold leading-tight fc-text-primary text-hero-gradient tracking-tight"
            >
              Multi-Agent Forensic
              <br />
              Evidence Analysis
            </motion.h1>

            <motion.p
              variants={itemVariants}
              className="text-lg md:text-xl fc-text-secondary font-medium leading-relaxed max-w-[68ch] mx-auto"
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

        <div
          className="absolute inset-x-0 bottom-0 h-24 pointer-events-none"
          style={{ background: "linear-gradient(to bottom, transparent, var(--color-background))" }}
          aria-hidden="true"
        />
      </section>

      {/* ── Content sections ── */}
      <div className="relative w-full px-4 sm:px-6 lg:px-8 pb-20 max-w-7xl mx-auto space-y-20">
        <div>
          <HowWorksSection />
        </div>

        <div>
          <AgentsSection />
        </div>
      </div>

    </div>
  );
}