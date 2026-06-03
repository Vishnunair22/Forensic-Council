"use client";

import { motion, useReducedMotion } from "framer-motion";
import { AGENTS } from "@/lib/constants";
import { SectionHeader } from "@/components/ui/SectionHeader";

export function AgentsSection() {
  const prefersReducedMotion = useReducedMotion();

  return (
    <section aria-labelledby="agents-heading" className="py-12 relative z-10">
      <SectionHeader
        headingId="agents-heading"
        eyebrow="Agents"
        titleLead="Meet the"
        titleAccent="Council"
        subtitle="Autonomous investigative agents optimized for multi-modal evidence consensus."
      />

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

            {/* Status — static; these agents are not running on the landing page */}
            <div className="mt-auto pt-5 border-t border-white/10 w-full flex items-center justify-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-success/70 shrink-0" aria-hidden="true" />
              <span className="text-xs fc-text-muted">Operational</span>
            </div>
          </motion.article>
        ))}
      </div>
    </section>
  );
}
