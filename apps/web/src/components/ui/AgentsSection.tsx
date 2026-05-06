"use client";

import { motion } from "framer-motion";
import { AGENTS } from "@/lib/constants";

/**
 * AgentsSection: A high-fidelity Bento Grid for the Forensic Council members.
 */
export function AgentsSection() {
  return (
    <section className="py-24 px-6 relative z-10 max-w-7xl mx-auto">
      <div className="text-center mb-16">
        <motion.h2
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-4xl md:text-5xl font-heading font-bold text-white mb-6"
        >
          Meet The <span className="text-primary">Council</span>
        </motion.h2>
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.1 }}
          className="text-base font-medium text-white/40 max-w-2xl mx-auto"
        >
          Autonomous neural investigative nodes optimized for multi-modal evidence consensus.
        </motion.p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
        {AGENTS.map((agent, i) => (
          <motion.div
            key={agent.id}
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.1, duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
            className="relative horizon-card p-8 rounded-3xl flex flex-col items-center text-center group cursor-pointer overflow-hidden border border-white/5 hover:border-primary/20 transition-all duration-500"
          >
            {/* --- Aperture Icon (Centered) --- */}
            <div className="relative w-16 h-16 flex items-center justify-center mb-6">
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
                className="absolute inset-0 rounded-full border border-primary/20 border-dashed"
              />
              <div className="absolute inset-2 rounded-full border border-primary/10 bg-primary/5" />
              <agent.icon className="w-7 h-7 text-primary group-hover:scale-110 transition-transform duration-500" />
            </div>

            <div className="mb-4">
               <span className="text-[10px] font-mono font-bold text-primary/60 tracking-[0.2em] uppercase bg-primary/5 px-3 py-1 rounded-full border border-primary/10">
                 {agent.badge}
               </span>
            </div>

            <div className="mb-4">
              <h3 className="text-xl font-heading font-bold text-white mb-3 tracking-tight">{agent.name}</h3>
              <p className="text-sm text-white/50 leading-relaxed font-medium group-hover:text-white/70 transition-colors duration-500 text-justify [text-align-last:center] [hyphens:auto]">
                {agent.desc}
              </p>
            </div>

            {/* --- Live Telemetry Feed (Centered) --- */}
            <div className="mt-auto pt-8 border-t border-white/5 w-full flex flex-col items-center gap-3">
              <div className="flex items-center gap-2">
                 <div className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse shadow-[0_0_8px_var(--color-primary)]" />
                 <span className="text-[10px] font-mono text-white/30 tracking-widest uppercase">
                   Node_{agent.id}_Active
                 </span>
              </div>
              <div className="text-[9px] font-mono text-primary/40 tracking-widest opacity-0 group-hover:opacity-100 transition-all duration-500 transform translate-y-2 group-hover:translate-y-0">
                LATENCY: {10 + i * 2}MS // UPTIME: 99.9%
              </div>
            </div>

            {/* Premium Glow Effect */}
            <div className="absolute inset-0 bg-gradient-to-b from-primary/5 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />
          </motion.div>
        ))}
      </div>
    </section>
  );
}
