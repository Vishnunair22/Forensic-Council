"use client";

import { motion } from "framer-motion";
import { AGENTS } from "@/lib/constants";

/**
 * AgentsSection: A high-fidelity Bento Grid for the Forensic Council members.
 */
export function AgentsSection() {
  return (
    <section className="py-24 px-6 relative z-10 max-w-7xl mx-auto">
      <div className="text-center mb-24">
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

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 auto-rows-[280px]">
        {AGENTS.map((agent, i) => {
          // Bento Grid logic: 
          // Agent 1 (Image) and Agent 6 (Arbiter) span 2 columns on large screens
          const isFeatured = i === 0 || i === 5;
          
          return (
            <motion.div
              key={agent.id}
              initial={{ opacity: 0, scale: 0.95 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1, duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
              className={`relative horizon-card p-8 rounded-2xl flex flex-col group cursor-pointer overflow-hidden ${
                isFeatured ? "lg:col-span-2" : "col-span-1"
              }`}
            >
              <div className="flex items-start justify-between mb-auto">
                {/* --- Aperture Icon (Horizon Signature) --- */}
                <div className="relative w-12 h-12 flex items-center justify-center">
                  <motion.div 
                    animate={{ rotate: 360 }}
                    transition={{ duration: 15, repeat: Infinity, ease: "linear" }}
                    className="absolute inset-0 rounded-full border border-primary/20 border-dashed"
                  />
                  <div className="absolute inset-2 rounded-full border border-primary/10" />
                  <agent.icon className="w-5 h-5 text-primary group-hover:scale-110 transition-transform" />
                </div>

                <div className="flex flex-col items-end">
                   <span className="text-[10px] font-mono font-bold text-primary/60 tracking-wider">
                     {agent.badge}
                   </span>
                </div>
              </div>
              
              <div className="mt-8">
                <h3 className="text-xl font-heading font-bold text-white mb-3">{agent.name}</h3>
                <p className="text-sm text-white/40 leading-relaxed font-medium line-clamp-2 group-hover:text-white/60 transition-colors">
                  {agent.desc}
                </p>
              </div>

              {/* --- Live Telemetry Feed --- */}
              <div className="mt-6 pt-6 border-t border-white/5 flex items-center justify-between">
                <div className="flex items-center gap-2">
                   <div className="w-1 h-1 rounded-full bg-success animate-pulse" />
                   <span className="text-[9px] font-mono text-white/30 tracking-widest uppercase">
                     Active_Node_{agent.id}
                   </span>
                </div>
                <div className="text-[9px] font-mono text-primary/40 tracking-tighter opacity-0 group-hover:opacity-100 transition-opacity">
                  LATENCY: {10 + i * 2}MS // INT_0.99
                </div>
              </div>

              {/* Glass Reflection overlay */}
              <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
            </motion.div>
          );
        })}
      </div>
    </section>
  );
}
