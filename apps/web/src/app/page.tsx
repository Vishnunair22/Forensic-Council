"use client";

import { motion } from "framer-motion";
import { HowWorksSection } from "@/components/ui/HowWorksSection";
import { AgentsSection } from "@/components/ui/AgentsSection";
import { HeroAuthActions } from "@/components/ui/HeroAuthActions";

export default function Home() {
  return (
    <div className="relative bg-black text-white min-h-screen">
      {/* --- Hero Section --- */}
      <div className="w-full min-h-screen flex flex-col items-center justify-center py-20">
        <div className="flex flex-col items-center justify-center text-center px-6 gap-10">
          <div className="flex flex-col items-center">
            <h1 className="text-5xl md:text-7xl font-bold tracking-tight leading-tight">
              Multi-Agent Forensic Evidence Analysis System
            </h1>
          </div>

          <p className="text-lg text-white/70 max-w-3xl mx-auto leading-relaxed">
            Forensic Council uses multiple customized agents to analyze digital forensic evidence to create a cohesive and effective report.
          </p>

          <div className="flex flex-col items-center">
            <HeroAuthActions />
          </div>
        </div>
      </div>

      {/* --- Content Section ---  */}
      <div className="w-full px-4 pb-32">
        <div className="bg-zinc-900 min-h-screen p-10 border border-white/10">
          <HowWorksSection />
          <AgentsSection />
        </div>
      </div>
    </div>
  );
}
