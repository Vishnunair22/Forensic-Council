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
          className="text-3xl md:text-5xl font-bold text-center mb-4 tracking-tight text-white font-heading"
        >
          Meet The <span className="text-primary">Council</span>
        </motion.h2>
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.1 }}
          className="text-sm font-medium text-white/40 text-center max-w-2xl mx-auto mb-20 font-sans"
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
              className="frosted-panel p-8 rounded-[2.5rem] flex flex-col items-center text-center group cursor-pointer shadow-2xl hover:-translate-y-2 hover:shadow-[0_20px_50px_rgba(0,0,0,0.4)] hover:border-primary/30 transition-all duration-500"
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
              
              <h3 className="font-bold text-xl mb-4 text-white tracking-tight font-heading">{agent.name}</h3>
              <p className="text-sm text-white/50 leading-relaxed font-medium tracking-tight mb-8 font-sans">
                {agent.desc}
              </p>

              <div className="mt-auto pt-6 border-t border-white/5 w-full flex justify-between items-center">
                 <span className="text-[10px] font-mono font-bold tracking-widest" style={{ color: `${agent.color}` }}>
                    Node {agent.id}
                 </span>
                 <span className="text-[10px] font-mono font-bold text-white/20 tracking-wider">[{agent.badge}]</span>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
