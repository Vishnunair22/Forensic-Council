"use client";

import { motion } from "framer-motion";
import { HOW_IT_WORKS } from "@/lib/constants";

export function HowWorksSection() {
  return (
    <section aria-labelledby="how-it-works-heading" className="py-12 px-4 sm:px-8 max-w-7xl mx-auto relative z-10">
      {/* Header */}
      <div className="text-center mb-14">
        <motion.p
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="text-[10px] font-mono font-bold tracking-[0.28em] text-primary/50 mb-4"
        >
          Process
        </motion.p>
        <motion.h2
          id="how-it-works-heading"
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          className="text-3xl sm:text-4xl md:text-[44px] font-heading font-bold text-white mb-4"
          style={{ letterSpacing: "-0.025em" }}
        >
          How Forensic{" "}
          <span style={{ color: "var(--color-primary-soft)" }}>Council Works</span>
        </motion.h2>
        <motion.p
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.08, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          className="text-sm sm:text-base font-medium text-slate-300/60 max-w-2xl mx-auto leading-relaxed"
        >
          A multi-stage verification pipeline ensuring cryptographic and semantic integrity
          through specialized AI coordination.
        </motion.p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-5">
        {HOW_IT_WORKS.map((item, i) => (
          <motion.div
            key={item.step}
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-40px" }}
            transition={{ duration: 0.65, delay: i * 0.12, ease: [0.16, 1, 0.3, 1] }}
            className="flex flex-col items-center"
          >
            {/* Step number + icon */}
            <div className="relative z-20 mb-5" aria-hidden="true">
              {/* Step number */}
              <div
                className="absolute -top-2 -right-2 w-5 h-5 rounded-full flex items-center justify-center z-10"
                style={{
                  background: "rgba(6,10,20,0.95)",
                  border: "1px solid rgba(165,200,255,0.15)",
                }}
              >
                <span className="text-[9px] font-mono font-bold" style={{ color: "rgba(165,200,255,0.5)" }}>
                  {String(i + 1).padStart(2, "0")}
                </span>
              </div>

              <motion.div
                whileHover={{ scale: 1.08 }}
                transition={{ type: "spring", stiffness: 320, damping: 24 }}
                className="w-14 h-14 rounded-2xl flex items-center justify-center"
                style={{
                  background: "linear-gradient(140deg, rgba(79,142,247,0.12), rgba(79,142,247,0.05))",
                  border: "1px solid rgba(79,142,247,0.18)",
                  boxShadow: "0 4px 20px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.06)",
                }}
              >
                <item.icon className="w-6 h-6" style={{ color: "var(--color-primary)" }} />
              </motion.div>
            </div>

            {/* Card */}
            <div className="w-full step-card p-6 rounded-2xl group relative overflow-hidden h-full">
              <h3
                className="text-[15px] font-heading font-bold text-white/90 mb-3 text-center"
                style={{ letterSpacing: "-0.015em" }}
              >
                {item.title}
              </h3>
              <p className="text-[13px] text-slate-300/55 leading-relaxed text-center">
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
