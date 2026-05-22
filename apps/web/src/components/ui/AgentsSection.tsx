"use client";

import { motion } from "framer-motion";
import { AGENTS } from "@/lib/constants";

export function AgentsSection() {
  return (
    <section aria-labelledby="agents-heading" className="py-12 px-4 sm:px-8 relative z-10 max-w-7xl mx-auto">
      <div className="mb-12 text-center">
        <motion.p
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="fc-eyebrow fc-text-faint mb-4"
        >
          Agents
        </motion.p>
        <motion.h2
          id="agents-heading"
          initial={{ opacity: 0, y: 4 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.16, ease: "easeOut" }}
          className="text-3xl sm:text-4xl font-heading font-black fc-text-primary mb-4 tracking-tight"
        >
          Meet the{" "}
          <span className="text-primary">Council</span>
        </motion.h2>
        <motion.p
          initial={{ opacity: 0, y: 4 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.16, ease: "easeOut" }}
          className="text-sm font-medium fc-text-secondary max-w-xl mx-auto leading-relaxed"
        >
          Autonomous investigative agents optimized for multi-modal evidence consensus.
        </motion.p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
        {AGENTS.map((agent, i) => (
          <motion.article
            key={agent.id}
            initial={{ opacity: 0, y: 4 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.16, delay: i * 0.04, ease: "easeOut" }}
            className="relative flex flex-col items-center text-center group overflow-hidden fc-surface-quiet p-6"
          >
            {/* Icon */}
            <div className="relative w-12 h-12 flex items-center justify-center mb-5 shrink-0 rounded-2xl bg-white/3 border border-white/10" aria-hidden="true">
              <agent.icon
                className="w-5 h-5 text-white/80"
              />
            </div>

            {/* Badge */}
            <div className="mb-4">
              <span className="fc-badge">
                {agent.badge}
              </span>
            </div>

            {/* Name & description */}
            <h3 className="text-lg font-heading font-black fc-text-primary mb-2 tracking-tight">
              {agent.name}
            </h3>
            <p className="text-sm fc-text-secondary leading-relaxed">
              {agent.desc}
            </p>

            {/* Status */}
            <div className="mt-auto pt-5 border-t border-white/10 w-full flex items-center justify-center gap-2" aria-hidden="true">
              <div
                className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse"
              />
              <span className="text-xs font-mono fc-text-muted">
                Node {agent.id} Active
              </span>
            </div>
          </motion.article>
        ))}
      </div>
    </section>
  );
}
