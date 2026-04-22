"use client";

import { motion } from "framer-motion";
import { HOW_IT_WORKS } from "@/lib/constants";

export function HowWorksSection() {
  return (
    <section className="py-24 px-6 max-w-7xl mx-auto text-center relative z-10">
      <motion.h2 
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        className="text-4xl md:text-6xl font-bold text-white mb-6 tracking-tighter"
      >
        How Forensic <span className="text-primary text-glow-green">Council Works</span>
      </motion.h2>
      <motion.p
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
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
            viewport={{ once: true }}
            transition={{ delay: i * 0.15, duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
            className="flex flex-col items-center group cursor-default"
          >
            {/* Icon Container (Liquid Glass) */}
            <div className="relative mb-12">
                <div className="absolute inset-0 bg-primary/20 blur-3xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-700 pointer-events-none" aria-hidden="true" />
                <motion.div 
                  animate={{ 
                    y: [0, -12, 0],
                  }}
                  transition={{
                    duration: 5,
                    repeat: Infinity,
                    ease: "easeInOut",
                    delay: i * 0.3
                  }}
                  className="relative p-8 glass-panel rounded-3xl group-hover:border-primary group-hover:shadow-[0_0_50px_rgba(0,255,65,0.1)] transition-all duration-500"
                >
                  <item.icon className="w-10 h-10 text-primary group-hover:scale-110 transition-transform duration-500" aria-hidden="true" />
                  <span className="absolute -top-3 -right-3 text-[10px] font-mono font-bold text-primary px-2.5 py-1 bg-black border border-primary/40 rounded-md shadow-lg group-hover:scale-110 transition-transform">
                    {item.step.padStart(2, '0')}
                  </span>
                </motion.div>
            </div>

            <div className="text-center px-4">
              <h4 className="text-xl font-bold mb-3 text-white tracking-tight group-hover:text-primary transition-colors">{item.title}</h4>
              <p className="text-sm text-white/60 leading-relaxed font-medium tracking-tight max-w-[240px] mx-auto group-hover:text-white/90 transition-colors">
                {item.desc}
              </p>
              
              <div className="mt-8 flex justify-center opacity-20 group-hover:opacity-100 transition-all duration-500 transform group-hover:translate-y-[-4px]">
                <span className="text-[10px] font-mono font-bold tracking-[0.2em] px-4 py-1.5 rounded-full border border-primary/30 text-primary uppercase">
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
