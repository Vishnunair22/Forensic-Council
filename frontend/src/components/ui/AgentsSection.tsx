"use client";

import { motion } from "framer-motion";
import { AGENTS } from "@/lib/constants";

export function AgentsSection() {
  return (
    <section className="py-24 relative overflow-hidden">
      <div className="max-w-7xl mx-auto px-6 relative z-10">
        <div className="text-center mb-12 max-w-2xl mx-auto">
          <motion.h2
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.4 }}
            className="text-4xl md:text-5xl font-bold text-white mb-6 tracking-tight"
          >
            Meet the Agents
          </motion.h2>
          <motion.p
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.4, delay: 0.08 }}
            className="text-white/50 text-sm md:text-base font-medium leading-relaxed"
          >
            Specialised agents deployed in every investigation.
          </motion.p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {AGENTS.map((agent, i) => (
            <motion.div
              key={agent.id}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.35, delay: i * 0.06 }}
              aria-label={`Forensic Agent: ${agent.name}, ${agent.badge}`}
              className="group relative flex flex-col p-8 rounded-2xl glass-panel overflow-hidden transition-colors duration-200 hover:border-sky-500/20"
              style={{ borderLeft: `2px solid ${agent.color}20` }}
            >
              <div className="relative z-10 flex flex-col items-center text-center">
                {/* Icon */}
                <div className="mb-8 w-16 h-16 rounded-xl flex items-center justify-center bg-white/[0.04] border border-white/[0.08] group-hover:border-white/[0.14] transition-colors duration-200">
                  <agent.icon
                    className="w-8 h-8"
                    style={{ color: agent.color }}
                  />
                </div>

                {/* Badge */}
                <div className="flex items-center gap-2 mb-3">
                  <span
                    className="w-1.5 h-1.5 rounded-full"
                    style={{ backgroundColor: agent.color }}
                  />
                  <span
                    className="text-[10px] font-bold uppercase tracking-[0.35em]"
                    style={{ color: agent.color }}
                  >
                    {agent.badge}
                  </span>
                </div>

                <h3 className="text-lg font-bold text-white mb-3 tracking-tight">
                  {agent.name}
                </h3>

                <p className="text-xs md:text-sm text-white/60 group-hover:text-white/80 transition-colors duration-200 leading-relaxed">
                  {agent.desc}
                </p>

                {/* Agent ID footer */}
                <div className="mt-6 pt-4 border-t border-white/[0.05] w-full flex justify-between items-center">
                  <span className="text-[9px] font-mono text-white/20">STATUS // READY</span>
                  <span className="text-[9px] font-mono" style={{ color: `${agent.color}60` }}>
                    {agent.id}
                  </span>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
