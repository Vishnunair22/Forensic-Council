"use client";

import { motion } from "framer-motion";
import { HOW_IT_WORKS } from "@/lib/constants";

export function HowWorksSection() {
  return (
    <section className="py-16 px-6 max-w-7xl mx-auto text-center bg-black relative z-10">
      <motion.h2 
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        className="text-3xl md:text-5xl font-black text-white mb-4 tracking-tighter"
      >
        How Forensic Council Works
      </motion.h2>
      <motion.p
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ delay: 0.1 }}
        className="text-slate-400 text-lg max-w-2xl mx-auto mb-20"
      >
        A transparent, multi-step process ensuring every piece of digital evidence is thoroughly vetted and cryptographically secured.
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
               <div className="absolute inset-0 bg-cyan-500/10 blur-3xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" aria-hidden="true" />
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
                  className="relative p-6 bg-white/[0.03] border border-white/5 rounded-3xl group-hover:border-cyan-500/30 transition-colors duration-300"
                >
                  <item.icon className="w-12 h-12 text-cyan-500 group-hover:scale-110 transition-transform duration-500" aria-hidden="true" />
                  <span className="absolute bottom-2 right-2 text-xs font-mono font-black text-cyan-500/40 px-1.5 py-0.5 bg-black/40 border border-white/5 rounded-md group-hover:text-cyan-400 group-hover:border-cyan-500/20 transition-colors duration-300">
                    {item.step}
                  </span>
               </motion.div>
            </div>

            <div className="text-center">
              <h4 className="text-xl font-bold mb-4 text-white tracking-tight group-hover:text-cyan-400 transition-colors">{item.title}</h4>
              <p className="text-slate-400 text-sm leading-relaxed max-w-[240px] mx-auto group-hover:text-slate-300 transition-colors">
                {item.desc}
              </p>
              
              <div className="mt-8 flex justify-center opacity-20 group-hover:opacity-60 transition-opacity">
                <span className="text-[10px] font-mono font-black tracking-[0.2em]" style={{ color: item.color }}>
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
