"use client";

import { motion } from "framer-motion";
import { HOW_IT_WORKS } from "@/lib/constants";

export function HowWorksSection() {
  return (
    <section className="py-24 px-6 max-w-7xl mx-auto text-center relative z-10">
      <motion.h2 
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, amount: 0.2 }}
        className="text-4xl md:text-6xl font-bold text-white mb-6 tracking-tighter"
      >
        How Forensic <span className="text-primary">Council Works</span>
      </motion.h2>
      <motion.p
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, amount: 0.2 }}
        transition={{ delay: 0.1 }}
        className="text-base font-medium text-white/60 max-w-2xl mx-auto mb-24"
      >
        A multi-stage neural verification pipeline ensuring the cryptographic and semantic integrity of digital media.
      </motion.p>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
        {HOW_IT_WORKS.map((item, i) => (
          <motion.div 
            key={item.step} 
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.2 }}
            transition={{ delay: i * 0.15, duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
            className="flex flex-col items-center group cursor-default"
          >
            {/* Icon Container (Liquid Glass) */}
            <div className="relative mb-12">
                <div className="absolute inset-0 bg-primary/20 blur-3xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-700 pointer-events-none" aria-hidden="true" />
                <motion.div 
                  animate={{ y: [0, -8, 0] }}
                  transition={{ duration: 6, repeat: Infinity, ease: "easeInOut", delay: i * 0.3 }}
                  className="relative p-6 bg-white/[0.04] backdrop-blur-xl rounded-3xl border border-white/10 group-hover:border-primary/30 group-hover:shadow-[0_20px_40px_rgba(0,0,0,0.4)] transition-all duration-500"
                >
                  <item.icon className="w-10 h-10 text-primary group-hover:scale-105 transition-transform duration-500" aria-hidden="true" />
                  <span className="absolute -top-3 -right-3 text-xs font-mono font-semibold text-primary px-3 py-1 bg-black/80 border border-primary/20 rounded-full shadow-[0_0_15px_rgba(0,255,65,0.1)] transition-transform duration-500">
                    {item.step.padStart(2, '0')}
                  </span>
                </motion.div>
            </div>

            <div className="text-center px-4">
              <h4 className="text-xl font-bold mb-3 text-white tracking-tight group-hover:text-primary transition-colors">{item.title}</h4>
              <p className="text-sm text-white/60 leading-relaxed font-medium tracking-tight max-w-[240px] mx-auto group-hover:text-white/90 transition-colors">
                {item.desc}
              </p>
              
              <div className="mt-8 flex justify-center transition-all duration-500">
                <span className="text-[10px] font-mono font-bold tracking-wide px-4 py-1.5 rounded-full border border-white/10 group-hover:border-primary/30 text-white/30 group-hover:text-primary transition-colors duration-500 bg-white/[0.02] group-hover:bg-primary/[0.05]">
                  {item.tag}
                </span>
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
