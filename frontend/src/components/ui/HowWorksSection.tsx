"use client";

import { motion } from "framer-motion";
import { HOW_IT_WORKS } from "@/lib/constants";

export function HowWorksSection() {
  return (
    <section className="py-24 relative overflow-hidden">
      <div className="max-w-7xl mx-auto px-6 relative z-10">
        <div className="text-center mb-20 max-w-2xl mx-auto">
          <motion.h2
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.4 }}
            className="text-4xl md:text-5xl font-bold text-white mb-6 tracking-tight"
          >
            How Forensic Council Works
          </motion.h2>
          <motion.p
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.4, delay: 0.08 }}
            className="text-white/50 text-sm md:text-base font-medium leading-relaxed"
          >
            Our multi-agent system ensures every artefact is meticulously
            analysed through a decentralised chain of custody.
          </motion.p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {HOW_IT_WORKS.map((item, i) => (
            <motion.div
              key={item.step}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.35, delay: i * 0.06 }}
              className="group relative flex flex-col p-8 rounded-2xl glass-panel transition-colors duration-200 hover:border-sky-500/20"
            >
              <div className="relative z-10 flex flex-col items-center text-center h-full">
                {/* Step number + icon */}
                <div className="relative mb-8 w-14 h-14 flex items-center justify-center">
                  <div className="absolute inset-0 rounded-xl border border-white/[0.08] bg-white/[0.03]" />
                  <item.icon className="relative z-10 w-7 h-7 text-white/80" />
                  <span
                    className="absolute -bottom-2 -right-2 text-xl font-black transition-transform duration-500 ease-out group-hover:-translate-y-[4.5rem]"
                    style={{ color: item.color }}
                  >
                    {parseInt(item.step)}
                  </span>
                </div>

                <h3 className="text-base md:text-lg font-bold text-white mb-3 tracking-tight">
                  {item.title}
                </h3>

                <p className="text-xs md:text-sm text-white/60 group-hover:text-white/80 transition-colors duration-200 font-medium leading-relaxed">
                  {item.desc}
                </p>

                {/* Tag chip */}
                <div className="mt-6 pt-4 border-t border-white/[0.05] w-full flex justify-center">
                  <span
                    className="text-[9px] font-mono font-bold uppercase tracking-widest px-2 py-1 rounded"
                    style={{
                      color: item.color,
                      backgroundColor: `${item.color}14`,
                    }}
                  >
                    {item.tag}
                  </span>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
