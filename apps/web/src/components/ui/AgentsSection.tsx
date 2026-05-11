"use client";

import { motion } from "framer-motion";
import { AGENTS } from "@/lib/constants";

export function AgentsSection() {
  return (
    <section aria-labelledby="agents-heading" className="py-12 px-4 sm:px-8 relative z-10 max-w-7xl mx-auto">
      <div className="text-center mb-12">
        <motion.p
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="text-[10px] font-mono font-bold tracking-[0.28em] text-primary/50 uppercase mb-4"
        >
          Agents
        </motion.p>
        <motion.h2
          id="agents-heading"
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          className="text-3xl sm:text-4xl md:text-[44px] font-heading font-bold text-white mb-4"
          style={{ letterSpacing: "-0.025em" }}
        >
          Meet the{" "}
          <span style={{ color: "var(--color-primary)" }}>Council</span>
        </motion.h2>
        <motion.p
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.08, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          className="text-sm font-medium text-slate-300/55 max-w-xl mx-auto leading-relaxed"
        >
          Autonomous investigative agents optimized for multi-modal evidence consensus.
        </motion.p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
        {AGENTS.map((agent, i) => (
          <motion.article
            key={agent.id}
            initial={{ opacity: 0, y: 18 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.07, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
            className="relative flex flex-col items-center text-center group overflow-hidden rounded-2xl p-6"
            style={{
              background: "rgba(6,10,20,0.85)",
              border: "1px solid rgba(165,200,255,0.07)",
              boxShadow: "0 8px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.04)",
              transition: "border-color 0.28s ease, box-shadow 0.28s ease, transform 0.28s cubic-bezier(0.16,1,0.3,1)",
            }}
            onMouseEnter={(e) => {
              const el = e.currentTarget as HTMLElement;
              el.style.borderColor = "rgba(79,142,247,0.20)";
              el.style.boxShadow = "0 12px 40px rgba(0,0,0,0.5), 0 0 30px rgba(79,142,247,0.07), inset 0 1px 0 rgba(255,255,255,0.05)";
              el.style.transform = "translateY(-2px)";
            }}
            onMouseLeave={(e) => {
              const el = e.currentTarget as HTMLElement;
              el.style.borderColor = "rgba(165,200,255,0.07)";
              el.style.boxShadow = "0 8px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.04)";
              el.style.transform = "";
            }}
          >
            {/* Icon */}
            <div className="relative w-14 h-14 flex items-center justify-center mb-5 shrink-0" aria-hidden="true">
              {/* Outer orbit ring */}
              <div
                className="absolute inset-0 rounded-full"
                style={{
                  border: "1px dashed rgba(79,142,247,0.15)",
                  animation: "fc-orbit 30s linear infinite",
                }}
              />
              {/* Inner fill */}
              <div
                className="absolute inset-2 rounded-full"
                style={{
                  background: "rgba(79,142,247,0.06)",
                  border: "1px solid rgba(79,142,247,0.10)",
                }}
              />
              <agent.icon
                className="w-6 h-6 relative z-10 transition-[color,transform] duration-300 group-hover:scale-110"
                style={{ color: "rgba(165,200,255,0.75)" }}
              />
            </div>

            {/* Badge */}
            <div className="mb-3">
              <span
                className="text-[9px] font-mono font-bold tracking-[0.22em] uppercase px-2.5 py-1 rounded-full"
                style={{
                  color: "rgba(79,142,247,0.65)",
                  background: "rgba(79,142,247,0.07)",
                  border: "1px solid rgba(79,142,247,0.12)",
                }}
              >
                {agent.badge}
              </span>
            </div>

            {/* Name & description */}
            <h3
              className="text-[17px] font-heading font-bold text-white/90 mb-2.5"
              style={{ letterSpacing: "-0.015em" }}
            >
              {agent.name}
            </h3>
            <p className="text-[13px] text-slate-300/50 leading-relaxed group-hover:text-slate-300/75 transition-colors duration-300">
              {agent.desc}
            </p>

            {/* Status */}
            <div className="mt-auto pt-5 border-t w-full flex items-center justify-center gap-2" style={{ borderColor: "rgba(255,255,255,0.05)" }} aria-hidden="true">
              <div
                className="w-1.5 h-1.5 rounded-full"
                style={{
                  background: "var(--color-primary)",
                  boxShadow: "0 0 8px rgba(79,142,247,0.7)",
                  animation: "pulse 2s ease-in-out infinite",
                }}
              />
              <span className="text-[9px] font-mono text-white/25 tracking-[0.2em] uppercase">
                Node_{agent.id}_Active
              </span>
            </div>

            {/* Top-edge glow on hover */}
            <div
              className="absolute inset-x-0 top-0 h-px opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"
              style={{ background: "linear-gradient(90deg, transparent 15%, rgba(79,142,247,0.5) 50%, transparent 85%)" }}
              aria-hidden="true"
            />
          </motion.article>
        ))}
      </div>
    </section>
  );
}
