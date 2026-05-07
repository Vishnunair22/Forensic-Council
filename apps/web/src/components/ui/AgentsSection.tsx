"use client";

import { motion } from "framer-motion";
import { AGENTS } from "@/lib/constants";

export function AgentsSection() {
  return (
    <section aria-labelledby="agents-heading" className="py-10 px-2 relative z-10 max-w-7xl mx-auto">
      <div className="text-center mb-12 sm:mb-14">
        <motion.h2
          id="agents-heading"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-3xl sm:text-4xl md:text-5xl font-heading font-bold text-white mb-5 tracking-tight"
        >
          Meet the <span className="text-primary">Council</span>
        </motion.h2>
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.1 }}
          className="text-base font-medium text-slate-300/80 max-w-2xl mx-auto leading-relaxed"
        >
          Autonomous neural investigative nodes optimized for multi-modal evidence consensus.
        </motion.p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 sm:gap-6">
        {AGENTS.map((agent, i) => (
          <motion.div
            key={agent.id}
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.08, duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
            className="relative horizon-card p-6 sm:p-7 rounded-2xl flex flex-col items-center text-center group overflow-hidden border border-white/[0.08] hover:border-primary/30 transition-[border-color] duration-300"
          >
            {/* Aperture icon ring */}
            <div className="relative w-16 h-16 flex items-center justify-center mb-6" aria-hidden="true">
              <div className="absolute inset-0 rounded-full border border-primary/[0.12] border-dashed [animation:spin_28s_linear_infinite]" />
              <div className="absolute inset-2 rounded-full border border-primary/[0.08] bg-primary/[0.04]" />
              <agent.icon className="w-7 h-7 text-primary/80 group-hover:text-primary group-hover:scale-110 transition-[color,transform] duration-300" />
            </div>

            <div className="mb-4">
              <span className="text-[10px] font-mono font-bold text-primary/60 tracking-[0.2em] uppercase bg-primary/5 px-3 py-1 rounded-full border border-primary/10">
                {agent.badge}
              </span>
            </div>

            <div className="mb-4">
              <h3 className="text-xl font-heading font-bold text-white mb-3 tracking-tight">{agent.name}</h3>
              <p className="text-sm text-slate-300/75 leading-relaxed font-medium group-hover:text-slate-100 transition-colors duration-300 text-center">
                {agent.desc}
              </p>
            </div>

            {/* Status indicator */}
            <div className="mt-auto pt-6 border-t border-white/5 w-full flex flex-col items-center gap-2" aria-hidden="true">
              <div className="flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse shadow-[0_0_8px_var(--color-primary)]" />
                <span className="text-[10px] font-mono text-slate-300/60 tracking-widest uppercase">
                  Node_{agent.id}_Active
                </span>
              </div>
              <div className="text-[9px] font-mono text-primary-soft/70 tracking-widest opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                LATENCY: {10 + i * 2}MS // UPTIME: 99.9%
              </div>
            </div>

            {/* Hover glow */}
            <div
              className="absolute inset-0 bg-gradient-to-b from-primary/5 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"
              aria-hidden="true"
            />
          </motion.div>
        ))}
      </div>
    </section>
  );
}
