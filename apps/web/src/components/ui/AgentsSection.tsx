"use client";

import { motion } from "framer-motion";
import { AGENTS } from "@/lib/constants";

export function AgentsSection() {
  return (
    <section className="py-24 px-6 bg-slate-900/10 rounded-t-[3rem] border-t border-white/5">
      <div className="max-w-7xl mx-auto px-6 relative z-10">
        <motion.h2 
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-3xl md:text-5xl font-black text-center mb-4 tracking-tighter text-white"
        >
          Meet The Agents
        </motion.h2>
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.1 }}
          className="text-slate-400 text-lg text-center max-w-2xl mx-auto mb-16"
        >
          Our specialized team of AI forensic experts work together to expose deepfakes, verify authenticity, and uncover the truth.
        </motion.p>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {AGENTS.map((agent, i) => (
            <motion.div
              key={agent.id}
              whileHover={{ y: -8, scale: 1.02 }}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1 }}
              className="glass-panel p-8 rounded-2xl border border-white/10 flex flex-col items-center text-center transition-all duration-300 group cursor-pointer"
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
                className="p-5 bg-white/[0.03] rounded-2xl mb-8 group-hover:bg-cyan-500/10 transition-colors"
              >
                <agent.icon
                  className="w-8 h-8 transition-transform group-hover:scale-110"
                  style={{ color: agent.color }}
                />
              </motion.div>
              
              <h3 className="font-bold text-lg mb-4 text-white tracking-tight">{agent.name}</h3>
              <p className="text-xs text-slate-400 leading-relaxed font-medium mb-8">
                {agent.desc}
              </p>

              <div className="mt-auto pt-6 border-t border-white/5 w-full flex justify-between items-center">
                 <span className="text-[10px] font-mono font-black tracking-[0.2em]" style={{ color: `${agent.color}80` }}>
                    {agent.id}
                 </span>
                 <span className="text-[10px] font-mono font-bold text-white/20 tracking-widest">{agent.badge}</span>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
