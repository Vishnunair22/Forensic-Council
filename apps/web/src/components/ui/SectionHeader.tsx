"use client";

import { motion, useReducedMotion } from "framer-motion";

interface SectionHeaderProps {
  /** id for the <h2>; referenced by the section's aria-labelledby */
  headingId: string;
  eyebrow: string;
  titleLead: string;
  titleAccent: string;
  subtitle: string;
}

export function SectionHeader({ headingId, eyebrow, titleLead, titleAccent, subtitle }: SectionHeaderProps) {
  const prefersReducedMotion = useReducedMotion();

  const fade = prefersReducedMotion
    ? {}
    : { initial: { opacity: 0 }, whileInView: { opacity: 1 }, viewport: { once: true } };

  const fadeUp = prefersReducedMotion
    ? {}
    : {
        initial: { opacity: 0, y: 4 },
        whileInView: { opacity: 1, y: 0 },
        viewport: { once: true },
        transition: { duration: 0.16, ease: "easeOut" as const },
      };

  return (
    <div className="mb-12 text-center">
      {/* Eyebrow flanked by hairline rules — quiet typographic framing */}
      <motion.div {...fade} className="flex items-center justify-center gap-3 mb-4">
        <span
          aria-hidden="true"
          className="h-px w-10"
          style={{ background: "linear-gradient(90deg, transparent, rgba(147,197,253,0.35))" }}
        />
        <p className="fc-eyebrow fc-text-muted">{eyebrow}</p>
        <span
          aria-hidden="true"
          className="h-px w-10"
          style={{ background: "linear-gradient(90deg, rgba(147,197,253,0.35), transparent)" }}
        />
      </motion.div>
      <motion.h2
        id={headingId}
        {...fadeUp}
        className="text-xl lg:text-3xl font-bold fc-text-primary mb-4"
      >
        {titleLead} <span className="text-primary">{titleAccent}</span>
      </motion.h2>
      <motion.p
        {...fadeUp}
        className="text-sm sm:text-base fc-text-secondary max-w-[60ch] mx-auto leading-relaxed"
      >
        {subtitle}
      </motion.p>
    </div>
  );
}
