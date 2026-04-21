"use client";

import { motion } from "framer-motion";
import { AGENTS } from "@/lib/constants";

export function AgentsSection() {
  return (
    <section className="py-24 px-6 bg-background rounded-t-[3rem] border-t border-border-bold">
      <div className="max-w-7xl mx-auto px-6 relative z-10">
        <motion.h2 
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-3xl md:text-5xl font-black text-center mb-4 tracking-tighter text-white"
        >
          Meet The <span className="text-primary">Council</span>
        </motion.h2>
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.1 }}
          className="text-[11px] font-black text-white/30 tracking-[0.3em] text-center max-w-2xl mx-auto mb-20"
        >
          Specialized investigative nodes optimized for multi-modal forensic consensus.
        </motion.p>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {AGENTS.map((agent, i) => (
            <motion.div
              key={agent.id}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1 }}
              className="premium-glass p-8 rounded-[2rem] border border-border-subtle flex flex-col items-center text-center transition-all duration-300 group cursor-pointer shadow-2xl"
            >
              <motion.div 
                animate={{ 
                  y: [0, -8, 0],
                }}
                transition={{
                  duration: 3 + i,
                  repeat: Infinity,
                  ease: "easeInOut",
                }}
                className="p-6 bg-surface-1 rounded-2xl mb-8 group-hover:bg-primary/10 transition-colors shadow-inner"
              >
                <agent.icon
                  className="w-8 h-8 transition-transform group-hover:scale-110"
                  style={{ color: agent.color }}
                />
              </motion.div>
              
              <h3 className="font-black text-lg mb-4 text-white tracking-tighter">{agent.name}</h3>
              <p className="text-[11px] text-white/40 leading-relaxed font-black tracking-tight mb-8">
                {agent.desc}
              </p>

              <div className="mt-auto pt-6 border-t border-border-subtle w-full flex justify-between items-center">
                 <span className="text-[9px] font-mono font-black tracking-[0.4em]" style={{ color: `${agent.color}80` }}>
                    Node_{agent.id}
                 </span>
                 <span className="text-[9px] font-mono font-black text-white/10 tracking-[0.2em]">[{agent.badge}]</span>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
