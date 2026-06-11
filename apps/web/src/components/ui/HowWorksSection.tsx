"use client";

import { motion, useReducedMotion } from "framer-motion";
import { HOW_IT_WORKS } from "@/lib/constants";
import { SectionHeader } from "@/components/ui/SectionHeader";

export function HowWorksSection() {
  const prefersReducedMotion = useReducedMotion();

  return (
    <section aria-labelledby="how-it-works-heading" className="py-12 relative z-10">
      <SectionHeader
        headingId="how-it-works-heading"
        eyebrow="Process"
        titleLead="How Forensic"
        titleAccent="Council Works"
        subtitle="A multi-stage verification pipeline ensuring cryptographic and semantic integrity through specialized AI coordination."
      />

      <div className="relative grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-5 xl:gap-6">
        {/* Pipeline connector — hairline through the icon row communicates the
            four steps as one sequential process (lg+ only, decorative) */}
        <div
          aria-hidden="true"
          className="hidden lg:block absolute top-7 left-[12%] right-[12%] h-px z-10 pointer-events-none"
          style={{
            background:
              "linear-gradient(90deg, transparent, rgba(147,197,253,0.22) 18%, rgba(147,197,253,0.22) 82%, transparent)",
          }}
        />
        {HOW_IT_WORKS.map((item, i) => (
          <motion.div
            key={item.step}
            {...(prefersReducedMotion ? {} : {
              initial: { opacity: 0, y: 4 },
              whileInView: { opacity: 1, y: 0 },
              viewport: { once: true, margin: "-40px" },
              transition: { duration: 0.16, delay: i * 0.04, ease: "easeOut" },
            })}
            className="group flex flex-col items-center"
          >
            {/* Step number + icon */}
            <div className="relative z-20 mb-5" aria-hidden="true">
              <div className="absolute -top-2.5 -right-2.5 w-8 h-8 rounded-full flex items-center justify-center z-10 bg-background border border-primary/25">
                <span className="text-xs font-mono font-bold fc-text-secondary">
                  {String(i + 1).padStart(2, "0")}
                </span>
              </div>

              <div
                className="relative overflow-hidden w-14 h-14 rounded-2xl flex items-center justify-center border border-primary/20 group-hover:border-primary/45 fc-transition fc-glass-highlight"
                style={{
                  // Solid base under the tint so the pipeline connector line
                  // terminates cleanly at the tile edges instead of showing through.
                  background:
                    "linear-gradient(180deg, rgba(var(--color-primary-rgb),0.10), rgba(255,255,255,0.03)), var(--color-background)",
                }}
              >
                <item.icon className="w-6 h-6 fc-text-secondary fc-transition group-hover:text-primary" />
              </div>
            </div>

            {/* Card */}
            <div className="w-full fc-surface-quiet rounded-2xl p-6 relative overflow-hidden h-full flex flex-col items-center fc-transition group-hover:border-primary/40">
              <h3 className="text-lg font-bold fc-text-primary mb-3 text-center tracking-tight">
                {item.title}
              </h3>
              <p className="text-sm fc-text-secondary leading-relaxed text-center">
                {item.desc}
              </p>

              {/* Subtle hover tint — color only, no movement */}
              <div
                className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-150 pointer-events-none"
                style={{
                  background: "radial-gradient(ellipse at 50% 0%, rgba(var(--color-primary-rgb),0.07), transparent 70%)",
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
