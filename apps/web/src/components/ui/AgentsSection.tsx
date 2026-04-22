"use client";

import { motion } from "framer-motion";
import { AGENTS } from "@/lib/constants";

export function AgentsSection() {
  return (
    <section className="py-24 px-6 relative z-10">
      <div className="max-w-7xl mx-auto px-6 relative z-10">
        <motion.h2 
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-4xl md:text-6xl font-bold text-center mb-6 tracking-tighter text-white"
        >
          Meet The <span className="text-primary text-glow-green">Council</span>
        </motion.h2>
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.1 }}
          className="text-base font-medium text-white/60 text-center max-w-2xl mx-auto mb-20"
        >
          Autonomous neural investigative nodes optimized for multi-modal evidence consensus.
        </motion.p>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {AGENTS.map((agent, i) => (
            <motion.div
              key={agent.id}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1, duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
              className="glass-panel p-10 rounded-[3rem] flex flex-col items-center text-center group cursor-pointer"
            >
              <motion.div 
                animate={{ 
                  y: [0, -10, 0],
                  scale: [1, 1.05, 1],
                }}
                transition={{
                  duration: 4 + i,
                  repeat: Infinity,
                  ease: "easeInOut",
                }}
                className="relative p-7 bg-white/5 rounded-2xl mb-10 group-hover:bg-primary/10 transition-colors"
              >
                <div className="absolute inset-0 bg-primary/20 blur-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                <agent.icon
                  className="relative z-10 w-10 h-10 transition-transform group-hover:scale-110"
                  style={{ color: agent.color }}
                />
              </motion.div>
              
              <h3 className="font-bold text-2xl mb-4 text-white tracking-tight">{agent.name}</h3>
              <p className="text-sm text-white/60 leading-relaxed font-medium tracking-tight mb-10 group-hover:text-white/90 transition-colors">
                {agent.desc}
              </p>

              <div className="mt-auto pt-8 border-t border-white/5 w-full flex justify-between items-center group-hover:border-primary/20 transition-colors">
                 <div className="flex flex-col items-start">
                   <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-white/20 group-hover:text-primary transition-colors">NODE_ID</span>
                   <span className="text-xs font-mono font-bold text-white/60">{agent.id}</span>
                 </div>
                 <div className="flex flex-col items-end">
                   <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-white/20 group-hover:text-primary transition-colors">STATUS</span>
                   <span className="text-xs font-mono font-bold text-primary/80 uppercase">{agent.badge}</span>
                 </div>
              </div>

              {/* Card Decoration: Corner Lines */}
              <div className="absolute top-6 left-6 w-4 h-4 border-t border-l border-white/10 group-hover:border-primary/40 transition-colors" />
              <div className="absolute bottom-6 right-6 w-4 h-4 border-b border-r border-white/10 group-hover:border-primary/40 transition-colors" />
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
