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
          className="fc-eyebrow text-white/55 mb-4"
        >
          Agents
        </motion.p>
        <motion.h2
          id="agents-heading"
          initial={{ opacity: 0, y: 5 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.3, ease: "easeOut" }}
          className="text-3xl sm:text-4xl md:text-[44px] font-heading font-black text-white mb-4 tracking-tight"
        >
          Meet the{" "}
          <span className="text-primary">Council</span>
        </motion.h2>
        <motion.p
          initial={{ opacity: 0, y: 5 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.3, ease: "easeOut" }}
          className="text-sm font-medium text-white/70 max-w-xl mx-auto leading-relaxed"
        >
          Autonomous investigative agents optimized for multi-modal evidence consensus.
        </motion.p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
        {AGENTS.map((agent, i) => (
          <motion.article
            key={agent.id}
            initial={{ opacity: 0, y: 5 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.3, delay: i * 0.05, ease: "easeOut" }}
            className="relative flex flex-col items-center text-center group overflow-hidden rounded-md p-6 bg-transparent transition-colors duration-200"
          >
            {/* Icon */}
            <div className="relative w-12 h-12 flex items-center justify-center mb-5 shrink-0 rounded-md bg-white/[0.03] border border-white/10" aria-hidden="true">
              <agent.icon
                className="w-5 h-5 text-white/80"
              />
            </div>

            {/* Badge */}
            <div className="mb-3">
              <span
                className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-sm bg-white/5 border border-white/10 text-white/60 uppercase"
              >
                {agent.badge}
              </span>
            </div>

            {/* Name & description */}
            <h3
              className="text-[16px] font-heading font-black text-white mb-2"
              style={{ letterSpacing: "-0.015em" }}
            >
              {agent.name}
            </h3>
            <p className="text-[13px] text-white/70 leading-relaxed group-hover:text-white/90 transition-colors duration-200">
              {agent.desc}
            </p>

            {/* Status */}
            <div className="mt-auto pt-5 border-t border-white/10 w-full flex items-center justify-center gap-2" aria-hidden="true">
              <div
                className="w-1.5 h-1.5 rounded-full bg-primary"
              />
              <span className="text-[10px] font-mono text-white/50">
                Node {agent.id} Active
              </span>
            </div>
          </motion.article>
        ))}
      </div>
    </section>
  );
}
