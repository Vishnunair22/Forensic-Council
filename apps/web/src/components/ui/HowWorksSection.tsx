"use client";

import { motion } from "framer-motion";
import { HOW_IT_WORKS } from "@/lib/constants";

export function HowWorksSection() {
  return (
    <section className="py-24 px-6 max-w-7xl mx-auto text-center bg-background relative z-10">
      <motion.h2 
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        className="text-3xl md:text-5xl font-black text-white mb-4 tracking-tighter"
      >
        How Forensic <span className="text-primary">Council Works</span>
      </motion.h2>
      <motion.p
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ delay: 0.1 }}
        className="text-[11px] font-black text-white/30 tracking-[0.3em] max-w-2xl mx-auto mb-24"
      >
        Multi-stage verification protocol ensuring cryptographic integrity and neural consistency.
      </motion.p>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-10">
        {HOW_IT_WORKS.map((item, i) => (
          <motion.div 
            key={item.step} 
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.1 }}
            className="flex flex-col items-center group"
          >
            {/* Icon Container */}
            <div className="relative mb-10">
                  <div className="absolute inset-0 bg-primary/10 blur-3xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" aria-hidden="true" />
               <motion.div 
                  animate={{ 
                    y: [0, -10, 0],
                  }}
                  transition={{
                    duration: 4,
                    repeat: Infinity,
                    ease: "easeInOut",
                    delay: i * 0.2
                  }}
                  className="relative p-7 premium-glass rounded-[2rem] group-hover:border-primary/40 transition-all duration-300 shadow-xl"
                >
                  <item.icon className="w-12 h-12 text-primary group-hover:scale-110 transition-transform duration-500" aria-hidden="true" />
                  <span className="absolute bottom-3 right-3 text-[10px] font-mono font-black text-primary/40 px-2 py-1 bg-surface-1 border border-border-subtle rounded-md group-hover:text-primary group-hover:border-primary/20 transition-colors duration-300">
                    SEQ_{item.step}
                  </span>
               </motion.div>
            </div>

            <div className="text-center">
              <h4 className="text-xl font-black mb-4 text-white tracking-tighter group-hover:text-primary transition-colors">{item.title}</h4>
              <p className="text-[11px] text-white/40 leading-relaxed font-black tracking-tight max-w-[240px] mx-auto group-hover:text-white/60 transition-colors">
                {item.desc}
              </p>
              
              <div className="mt-8 flex justify-center opacity-20 group-hover:opacity-60 transition-opacity">
                <span className="text-[9px] font-mono font-black tracking-[0.3em]" style={{ color: item.color }}>
                  [{item.tag}]
                </span>
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
