"use client";

import { motion, useReducedMotion } from "framer-motion";
import { HOW_IT_WORKS } from "@/lib/constants";

export function HowWorksSection() {
  const prefersReducedMotion = useReducedMotion();

  const fadeUp = prefersReducedMotion
    ? {}
    : { initial: { opacity: 0, y: 4 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true } };

  const fade = prefersReducedMotion
    ? {}
    : { initial: { opacity: 0 }, whileInView: { opacity: 1 }, viewport: { once: true } };

  return (
    <section aria-labelledby="how-it-works-heading" className="py-12 relative z-10">
      {/* Header */}
      <div className="mb-14 text-center">
        <motion.p
          {...fade}
          className="fc-eyebrow fc-text-muted mb-4"
        >
          Process
        </motion.p>
        <motion.h2
          id="how-it-works-heading"
          {...fadeUp}
          transition={{ duration: 0.16, ease: "easeOut" }}
          className="text-xl lg:text-3xl font-bold fc-text-primary mb-4 tracking-tight"
        >
          How Forensic{" "}
          <span className="text-primary">Council Works</span>
        </motion.h2>
        <motion.p
          {...fadeUp}
          transition={{ duration: 0.16, ease: "easeOut" }}
          className="text-sm sm:text-base fc-text-secondary max-w-[68ch] mx-auto leading-relaxed"
        >
          A multi-stage verification pipeline ensuring cryptographic and semantic integrity
          through specialized AI coordination.
        </motion.p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-5 xl:gap-6">
        {HOW_IT_WORKS.map((item, i) => (
          <motion.div
            key={item.step}
            {...(prefersReducedMotion ? {} : {
              initial: { opacity: 0, y: 4 },
              whileInView: { opacity: 1, y: 0 },
              viewport: { once: true, margin: "-40px" },
              transition: { duration: 0.16, delay: i * 0.04, ease: "easeOut" },
            })}
            className="flex flex-col items-center"
          >
            {/* Step number + icon */}
            <div className="relative z-20 mb-5" aria-hidden="true">
              <div className="absolute -top-2.5 -right-2.5 w-8 h-8 rounded-full flex items-center justify-center z-10 bg-background border border-white/10">
                <span className="text-xs font-mono font-bold fc-text-secondary">
                  {String(i + 1).padStart(2, "0")}
                </span>
              </div>

              <div className="w-14 h-14 rounded-2xl flex items-center justify-center bg-white/5 border border-white/10">
                <item.icon className="w-6 h-6 fc-text-secondary fc-transition group-hover:text-primary" />
              </div>
            </div>

            {/* Card */}
            <div className="w-full fc-surface-quiet rounded-2xl p-6 relative overflow-hidden h-full flex flex-col items-center group fc-transition hover:border-primary/40">
              <h3 className="text-lg font-bold fc-text-primary mb-3 text-center tracking-tight">
                {item.title}
              </h3>
              <p className="text-sm fc-text-secondary leading-relaxed text-center">
                {item.desc}
              </p>

              {/* Subtle hover tint — color only, no movement */}
              <div
                className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-150 pointer-events-none"
                style={{
                  background: "radial-gradient(ellipse at 50% 0%, rgba(var(--color-primary-rgb),0.07), transparent 70%)",
                }}
                aria-hidden="true"
              />
            </div>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
