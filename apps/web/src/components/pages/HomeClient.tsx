"use client";

import dynamic from "next/dynamic";
import { HeroAuthActions } from "@/components/ui/HeroAuthActions";
import { motion, type Variants } from "framer-motion";
import { useReducedMotionSafe } from "@/hooks/useReducedMotionSafe";

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
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: 0.22, ease: [0.16, 1, 0.3, 1] } },
};

export function HomeClient() {
  const prefersReducedMotion = useReducedMotionSafe();
  return (
    <div className="relative min-h-screen">
      {/* Single dot-grid texture — LandingBackground (layout.tsx) supplies the ambient glows */}
      <div
        className="absolute inset-0 overflow-hidden pointer-events-none -z-10 bg-dot-grid opacity-30 [mask-image:radial-gradient(ellipse_at_center,white_50%,transparent_100%)]"
        aria-hidden="true"
      />

      {/* ── Hero ── */}
      <section id="hero" aria-labelledby="hero-heading" className="relative w-full min-h-screen flex flex-col items-center justify-center pb-24 px-5 sm:px-6">

        <motion.div
          variants={prefersReducedMotion ? undefined : containerVariants}
          initial={prefersReducedMotion ? false : "hidden"}
          animate={prefersReducedMotion ? false : "show"}
          className="flex flex-col items-center text-center w-full max-w-4xl mx-auto z-10"
        >
          {/* Headline */}
          <div className="space-y-7 mb-14 w-full">
            <motion.h1
              id="hero-heading"
              variants={itemVariants}
              className="text-4xl sm:text-5xl lg:text-6xl xl:text-7xl font-extrabold leading-[1.08] tracking-[-0.03em] text-hero-gradient text-glow text-balance"
            >
              Multi-Agent Forensic Evidence Analysis
            </motion.h1>

            <motion.p
              variants={itemVariants}
              className="text-lg md:text-xl fc-text-secondary font-medium leading-relaxed text-balance max-w-[52ch] mx-auto"
            >
              Forensic Council deploys specialized AI agents to analyze digital evidence,
              synthesizing cohesive, cryptographically-signed reports with chain-of-custody integrity.
            </motion.p>
          </div>

          {/* CTA — soft radial halo behind the button gives the single primary
              action a focal stage (background gradient, not a box-shadow, so it
              stays inside the no-neon-shadow rule) */}
          <motion.div variants={itemVariants} className="mt-2 relative">
            <div
              aria-hidden="true"
              className="absolute -inset-x-20 -inset-y-10 pointer-events-none"
              style={{
                background:
                  "radial-gradient(ellipse at center, rgba(var(--color-primary-rgb),0.13), transparent 70%)",
                filter: "blur(14px)",
              }}
            />
            <HeroAuthActions />
          </motion.div>

        </motion.div>

        {/* Scroll affordance — hairline + status dot (animate-pulse is permitted
            on w-1.5 indicator dots; suppressed automatically by reduced-motion) */}
        <div
          aria-hidden="true"
          className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 pointer-events-none"
        >
          <div
            className="w-px h-10"
            style={{
              background:
                "linear-gradient(to bottom, transparent, rgba(147,197,253,0.45))",
            }}
          />
          <div className="w-1.5 h-1.5 rounded-full bg-primary/70 animate-pulse" />
        </div>

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