"use client";

import { motion } from "framer-motion";
import { HOW_IT_WORKS } from "@/lib/constants";

export function HowWorksSection() {
  return (
    <section aria-labelledby="how-it-works-heading" className="py-12 px-4 sm:px-8 max-w-7xl mx-auto relative z-10">
      {/* Header */}
      <div className="mb-14 text-center">
        <motion.p
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="fc-eyebrow fc-text-faint mb-4"
        >
          Process
        </motion.p>
        <motion.h2
          id="how-it-works-heading"
          initial={{ opacity: 0, y: 4 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.16, ease: "easeOut" }}
          className="text-3xl sm:text-4xl font-heading font-black text-white mb-4 tracking-tight"
        >
          How Forensic{" "}
          <span className="text-primary">Council Works</span>
        </motion.h2>
        <motion.p
          initial={{ opacity: 0, y: 4 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.16, ease: "easeOut" }}
          className="text-sm sm:text-base font-medium fc-text-secondary max-w-2xl mx-auto leading-relaxed"
        >
          A multi-stage verification pipeline ensuring cryptographic and semantic integrity
          through specialized AI coordination.
        </motion.p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-5">
        {HOW_IT_WORKS.map((item, i) => (
          <motion.div
            key={item.step}
            initial={{ opacity: 0, y: 4 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-40px" }}
            transition={{ duration: 0.16, delay: i * 0.04, ease: "easeOut" }}
            className="flex flex-col items-center"
          >
            {/* Step number + icon */}
            <div className="relative z-20 mb-5" aria-hidden="true">
              {/* Step number */}
              <div
                className="absolute -top-2 -right-2 w-5 h-5 rounded-full flex items-center justify-center z-10 bg-[#02040A] border border-white/10"
              >
                <span className="text-xs font-mono font-bold fc-text-faint">
                  {String(i + 1).padStart(2, "0")}
                </span>
              </div>

              <div
                className="w-14 h-14 rounded-xl flex items-center justify-center bg-white/[0.03] border border-white/10"
              >
                <item.icon className="w-6 h-6 text-white/80" />
              </div>
            </div>

            {/* Card */}
            <div className="w-full fc-surface-quiet p-6 relative overflow-hidden h-full flex flex-col items-center">
              <h3
                className="text-base font-heading font-black text-white mb-3 text-center"
                style={{ letterSpacing: "-0.015em" }}
              >
                {item.title}
              </h3>
              <p className="text-sm fc-text-secondary leading-relaxed text-center">
                {item.desc}
              </p>

              {/* Hover glow */}
              <div
                className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-400 pointer-events-none"
                style={{
                  background: "radial-gradient(ellipse at 50% 0%, rgba(79,142,247,0.07), transparent 70%)",
                }}
                aria-hidden="true"
              />
            </div>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
