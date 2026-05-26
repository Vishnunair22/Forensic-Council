"use client";

import { motion, useReducedMotion } from "framer-motion";
import { AGENTS } from "@/lib/constants";

export function AgentsSection() {
  const prefersReducedMotion = useReducedMotion();

  const fadeUp = prefersReducedMotion
    ? {}
    : { initial: { opacity: 0, y: 4 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true } };

  const fade = prefersReducedMotion
    ? {}
    : { initial: { opacity: 0 }, whileInView: { opacity: 1 }, viewport: { once: true } };

  return (
    <section aria-labelledby="agents-heading" className="py-12 relative z-10">
      <div className="mb-12 text-center">
        <motion.p
          {...fade}
          className="fc-eyebrow fc-text-muted mb-4"
        >
          Agents
        </motion.p>
        <motion.h2
          id="agents-heading"
          {...fadeUp}
          transition={{ duration: 0.16, ease: "easeOut" }}
          className="text-xl lg:text-3xl font-bold fc-text-primary mb-4 tracking-tight"
        >
          Meet the{" "}
          <span className="text-primary">Council</span>
        </motion.h2>
        <motion.p
          {...fadeUp}
          transition={{ duration: 0.16, ease: "easeOut" }}
          className="text-sm sm:text-base fc-text-secondary max-w-[68ch] mx-auto leading-relaxed"
        >
          Autonomous investigative agents optimized for multi-modal evidence consensus.
        </motion.p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 md:gap-5 xl:gap-6">
        {AGENTS.map((agent, i) => (
          <motion.article
            key={agent.id}
            {...(prefersReducedMotion ? {} : {
              initial: { opacity: 0, y: 4 },
              whileInView: { opacity: 1, y: 0 },
              viewport: { once: true },
              transition: { duration: 0.16, delay: i * 0.04, ease: "easeOut" },
            })}
            className="relative flex flex-col items-center text-center group overflow-hidden fc-surface-quiet rounded-2xl p-7 sm:p-8 fc-transition hover:border-primary/40"
          >
            {/* Icon */}
            <div
              className="relative w-12 h-12 flex items-center justify-center mb-5 shrink-0 rounded-2xl bg-white/5 border border-white/10"
              aria-hidden="true"
            >
              <agent.icon className="w-5 h-5 fc-text-secondary fc-transition group-hover:text-primary" />
            </div>

            {/* Badge */}
            <div className="mb-4">
              <span className="fc-badge">{agent.badge}</span>
            </div>

            {/* Name & description */}
            <h3 className="text-lg font-bold fc-text-primary mb-2 tracking-tight">
              {agent.name}
            </h3>
            <p className="text-sm fc-text-secondary leading-relaxed max-w-[44ch] mx-auto">
              {agent.desc}
            </p>

            {/* Status — static dot, not animate-pulse; these agents are not running on the landing page */}
            <div className="mt-auto pt-5 border-t border-white/10 w-full flex items-center justify-center gap-2">
              <div
                className="w-1.5 h-1.5 rounded-full bg-primary/60 shrink-0 fc-transition group-hover:bg-success"
                aria-hidden="true"
              />
              <span className="text-xs fc-text-muted fc-transition group-hover:text-primary">
                {agent.name} · Operational
              </span>
            </div>
          </motion.article>
        ))}
      </div>
    </section>
  );
}
