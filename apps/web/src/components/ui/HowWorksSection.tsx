"use client";

import { motion } from "framer-motion";
import { HOW_IT_WORKS } from "@/lib/constants";

/**
 * HowWorksSection: A vertical "Neural Path" layout for the Horizon theme.
 */
export function HowWorksSection() {
  return (
    <section className="py-24 px-6 max-w-5xl mx-auto relative z-10">
      <div className="text-center mb-32">
        <motion.h2 
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-4xl md:text-5xl font-heading font-bold text-white mb-6"
        >
          How Forensic <span className="text-primary">Council Works</span>
        </motion.h2>
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.1 }}
          className="text-base font-medium text-white/40 max-w-2xl mx-auto"
        >
          A multi-stage neural verification pipeline ensuring the cryptographic and semantic integrity of digital media.
        </motion.p>
      </div>

      <div className="relative">
        {/* --- Central Connecting Line (The Neural Path) --- */}
        <div className="absolute left-[31px] md:left-1/2 top-0 bottom-0 w-[1px] bg-gradient-to-b from-primary/40 via-primary/10 to-transparent -translate-x-1/2 hidden md:block" />

        <div className="space-y-24">
          {HOW_IT_WORKS.map((item, i) => (
            <motion.div 
              key={item.step}
              initial={{ opacity: 0, x: i % 2 === 0 ? -30 : 30 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true, margin: "-100px" }}
              transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }}
              className={`flex flex-col md:flex-row items-center gap-12 ${i % 2 === 0 ? 'md:flex-row' : 'md:flex-row-reverse'}`}
            >
              {/* Step Card */}
              <div className="flex-1 w-full">
                <div className="horizon-card p-8 rounded-2xl group relative overflow-hidden">
                  <div className="flex items-center gap-4 mb-4">
                    <span className="text-xs font-mono font-bold text-primary/60 border border-primary/20 px-2 py-0.5 rounded bg-primary/5">
                      {item.step.padStart(2, '0')}
                    </span>
                    <h4 className="text-xl font-heading font-bold text-white">{item.title}</h4>
                  </div>
                  <p className="text-sm text-white/50 leading-relaxed font-medium">
                    {item.desc}
                  </p>
                  
                  {/* Hover Decoration */}
                  <div className="absolute top-0 right-0 w-24 h-24 bg-primary/5 blur-3xl opacity-0 group-hover:opacity-100 transition-opacity" />
                </div>
              </div>

              {/* Central Icon Node */}
              <div className="relative z-20 flex-shrink-0">
                <motion.div
                  whileInView={{ scale: [1, 1.2, 1], borderColor: ["rgba(0,255,255,0.2)", "rgba(0,255,255,0.6)", "rgba(0,255,255,0.2)"] }}
                  transition={{ duration: 2, repeat: Infinity }}
                  className="w-16 h-16 rounded-full bg-[#0F172A] border border-primary/20 flex items-center justify-center shadow-[0_0_30px_rgba(0,255,255,0.1)]"
                >
                  <item.icon className="w-7 h-7 text-primary" />
                </motion.div>
                
                {/* Horizontal connection stub */}
                <div className={`absolute top-1/2 w-12 h-[1px] bg-primary/20 -translate-y-1/2 hidden md:block ${i % 2 === 0 ? 'left-16' : 'right-16'}`} />
              </div>

              {/* Empty space for the zig-zag on desktop */}
              <div className="flex-1 hidden md:block" />
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
