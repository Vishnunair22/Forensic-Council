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
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8 relative z-10">
          {HOW_IT_WORKS.map((item, i) => (
            <motion.div 
              key={item.step}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-50px" }}
              transition={{ duration: 0.8, delay: i * 0.2, ease: [0.16, 1, 0.3, 1] }}
              className="flex flex-col items-center"
            >
              {/* Step Icon Node */}
              <div className="relative z-20 mb-8">
                <motion.div
                  whileHover={{ scale: 1.1 }}
                  whileInView={{ 
                    boxShadow: ["0 0 0px rgba(0,255,255,0)", "0 0 40px rgba(0,255,255,0.2)", "0 0 0px rgba(0,255,255,0)"] 
                  }}
                  transition={{ duration: 3, repeat: Infinity }}
                  className="w-20 h-20 rounded-2xl bg-slate-900/50 border border-primary/20 flex items-center justify-center backdrop-blur-sm"
                >
                  <item.icon className="w-10 h-10 text-primary" />
                </motion.div>
              </div>

              {/* Step Card */}
              <div className="w-full text-center">
                <div className="horizon-card p-8 rounded-3xl group relative overflow-hidden h-full border border-white/5 hover:border-primary/20 transition-colors">
                  <h4 className="text-xl font-heading font-bold text-white mb-4">{item.title}</h4>
                  <p className="text-sm text-white/50 leading-relaxed font-medium text-justify [text-align-last:center] [hyphens:auto]">
                    {item.desc}
                  </p>
                  
                  {/* Decorative Gradient Background */}
                  <div className="absolute inset-0 bg-gradient-to-b from-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
