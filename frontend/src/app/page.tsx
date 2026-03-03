"use client";

import { motion } from "framer-motion";
import { ChevronRight, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";
import { AGENTS_DATA } from "@/lib/constants";
import { AgentIcon } from "@/components/ui/AgentIcon";
import { useSound } from "@/hooks/useSound";

export default function LandingPage() {
  const { playSound } = useSound();

  // Force scroll to top on mount
  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  return (
    <div className="relative bg-[#050505] text-white overflow-x-hidden">
      {/* Global Background Elements */}
      <div className="fixed inset-0 z-0 pointer-events-none" aria-hidden="true">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff05_1px,transparent_1px),linear-gradient(to_bottom,#ffffff05_1px,transparent_1px)] bg-[size:32px_32px]"></div>
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[500px] bg-cyan-900/20 rounded-full blur-[120px] mix-blend-screen"></div>
        <div className="absolute bottom-0 left-0 w-[500px] h-[500px] bg-purple-900/10 rounded-full blur-[100px] mix-blend-screen"></div>
      </div>

      <header className="fixed top-0 w-full p-6 flex items-center justify-between border-b border-white/5 bg-black/40 backdrop-blur-xl z-50">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 bg-gradient-to-br from-cyan-400 to-blue-600 rounded flex items-center justify-center font-bold text-slate-900 shadow-[0_0_15px_rgba(34,211,238,0.4)]">FC</div>
          <span className="text-xl font-bold tracking-tight bg-gradient-to-r from-white to-slate-400 bg-clip-text text-transparent">Forensic Council</span>
        </div>
      </header>

      {/* --- Hero Section --- */}
      <section className="relative w-full min-h-screen flex flex-col items-center justify-center px-6 pt-20 z-10 overflow-hidden">
        {/* Subtle Evidence Scanner Background (Hero Only) */}
        <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none mix-blend-screen isolate" aria-hidden="true">
          {/* Central Grid Lock */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] border border-cyan-500/5 rounded-full flex items-center justify-center">
            <div className="w-[400px] h-[400px] border border-cyan-500/10 border-dashed rounded-full" />
          </div>
          {/* Tracking Reticles */}
          <div className="absolute top-1/4 left-[15%] w-32 h-32 border border-cyan-500/20 rounded-full flex items-center justify-center animate-pulse">
            <div className="w-1 h-1 bg-cyan-400 rounded-full shadow-[0_0_10px_rgba(34,211,238,1)]" />
            <div className="absolute w-full h-[1px] bg-cyan-500/20" />
            <div className="absolute h-full w-[1px] bg-cyan-500/20" />
          </div>
          <div className="absolute bottom-1/3 right-[15%] w-48 h-48 border border-emerald-500/10 rounded-full flex items-center justify-center animate-[pulse_4s_infinite]">
            <div className="w-1.5 h-1.5 bg-emerald-400/50 rounded-full shadow-[0_0_10px_rgba(16,185,129,1)]" />
            <div className="absolute w-full h-[1px] bg-emerald-500/10" />
            <div className="absolute h-full w-[1px] bg-emerald-500/10" />
          </div>
          {/* Horizontal Scanner Line */}
          <motion.div
            animate={{ top: ["0%", "100%", "0%"] }}
            transition={{ duration: 12, ease: "linear", repeat: Infinity }}
            className="absolute left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-cyan-400/50 to-transparent shadow-[0_0_20px_rgba(34,211,238,0.4)] z-10"
          />
          {/* Vignette to fade out edges */}
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,rgba(5,5,5,1)_80%)] z-20" />
        </div>

        <div className="flex flex-col items-center justify-center text-center max-w-5xl mx-auto relative z-30">
          <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.8, ease: "easeOut" }} className="mb-6 inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/5 border border-white/10 text-sm text-cyan-400 backdrop-blur-md">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500"></span>
            </span>
            System Online
          </motion.div>
          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: "easeOut" }}
            className="text-4xl sm:text-5xl md:text-7xl font-extrabold mb-6 tracking-tighter text-transparent bg-clip-text bg-gradient-to-b from-white to-slate-400 drop-shadow-sm pb-2"
          >
            Multi-Agent Forensic Evidence Analysis System
          </motion.h1>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2, duration: 0.8 }}
            className="text-slate-300 text-base sm:text-xl max-w-2xl mb-10 leading-relaxed font-light"
          >
            This system leverages multiple specialized intelligent agents that independently analyze digital forensic evidence and synthesize their findings into a cohesive, court-ready report.
          </motion.p>
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}>
            <Link onClick={() => playSound("upload")} href="/evidence" className="group relative px-10 py-5 bg-gradient-to-r from-emerald-500 to-cyan-500 text-white text-lg font-bold rounded-full overflow-hidden transition-all hover:scale-105 hover:shadow-[0_0_60px_rgba(16,185,129,0.5)] border border-white/20 inline-flex items-center focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-cyan-500 focus-visible:ring-offset-4 focus-visible:ring-offset-[#050505]">
              <span className="relative z-10 flex items-center">
                Begin Analysis <ChevronRight aria-hidden="true" className="ml-2 w-6 h-6 group-hover:translate-x-2 transition-transform" />
              </span>
            </Link>
          </motion.div>
        </div>
      </section>

      {/* --- How it Works ---  */}
      <section className="relative z-10 py-32 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-20">
            <h2 className="text-3xl md:text-5xl font-bold bg-white bg-clip-text text-transparent">How Forensic Council Works</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-8 relative">
            {/* Connecting line for desktop */}
            <div className="hidden md:block absolute top-[60px] left-[10%] right-[10%] h-[1px] bg-gradient-to-r from-transparent via-cyan-500/50 to-transparent"></div>

            {[
              { step: "01", title: "Evidence Intake", desc: "Upload digital media artifacts including CCTV, photographs, or raw extracted metadata." },
              { step: "02", title: "Agent Consultation", desc: "Specialized analytical agents process the data stream concurrently, identifying anomalies." },
              { step: "03", title: "Arbiter Synthesis", desc: "The Council Arbiter evaluates findings, resolving contradictions and calculating confidence scores." },
              { step: "04", title: "Final Verdict", desc: "A cryptographically signed final report is generated, detailing the forensic analysis." }
            ].map((item, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.2, duration: 0.6 }}
                className="relative p-8 rounded-3xl bg-slate-900/40 border border-white/10 backdrop-blur-2xl flex flex-col items-center text-center mt-6 group hover:border-cyan-500/30 hover:bg-cyan-900/10 hover:shadow-[0_0_40px_rgba(34,211,238,0.05)] transition-all overflow-visible"
              >
                {/* Subtle glass reflection */}
                <div className="absolute inset-0 rounded-3xl bg-gradient-to-b from-white/[0.05] to-transparent opacity-0 group-hover:opacity-100 transition-opacity" aria-hidden="true" />
                <div className="absolute -top-8 w-16 h-16 rounded-full bg-[#050505] border border-cyan-500/30 flex items-center justify-center font-mono text-xl text-cyan-400 font-bold shadow-[0_0_20px_rgba(34,211,238,0.15)] group-hover:scale-110 transition-transform z-10" aria-hidden="true">
                  {item.step}
                </div>
                <h3 className="text-xl font-bold mb-4 mt-6 text-white relative z-10">{item.title}</h3>
                <p className="text-slate-300 text-sm leading-relaxed font-normal relative z-10">{item.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* --- Meet the Agents ---  */}
      <section className="relative z-10 pb-32 pt-16 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-5xl font-bold mb-6 bg-gradient-to-r from-cyan-400 to-purple-400 bg-clip-text text-transparent inline-block">Meet the Council</h2>
            <p className="text-slate-400 text-lg max-w-2xl mx-auto font-light">Five specialist agents analyze evidence independently, then the Council Arbiter synthesizes their findings into a unified verdict.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {AGENTS_DATA.map((agent, i) => (
              <motion.div
                key={agent.id}
                initial={{ opacity: 0, y: 40 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-100px" }}
                transition={{ delay: i * 0.1, duration: 0.6, ease: "easeOut" }}
                whileHover={{ y: -8, scale: 1.02 }}
                className="p-8 rounded-3xl bg-gradient-to-br from-slate-900/60 to-black/40 backdrop-blur-3xl border border-white/10 hover:border-cyan-400/40 flex flex-col items-center text-center transition-all duration-300 shadow-[0_8px_32px_rgba(0,0,0,0.5)] hover:shadow-[0_8px_32px_rgba(34,211,238,0.15)] group relative overflow-hidden"
              >
                <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 rounded-3xl" aria-hidden="true"></div>
                <div className="p-4 bg-cyan-500/10 text-cyan-400 rounded-2xl mb-6 shadow-[inset_0_0_20px_rgba(34,211,238,0.05)] border border-cyan-500/20 relative z-10" aria-hidden="true">
                  <AgentIcon role={agent.role} />
                </div>
                <h3 className="text-xl font-semibold mb-2 text-white relative z-10">{agent.name}</h3>
                <span className="text-[11px] px-3 py-1 rounded-full bg-cyan-950/50 text-cyan-300 border border-cyan-500/20 uppercase tracking-widest font-semibold mb-4 relative z-10">{agent.role}</span>
                <p className="text-sm text-slate-300 leading-relaxed mb-6 font-normal relative z-10 flex-1">{agent.desc}</p>
                <div className="w-full pt-4 border-t border-white/5 relative z-10">
                  <p className="text-xs text-cyan-500 font-mono italic leading-relaxed">&quot;{agent.simulation.thinking}&quot;</p>
                </div>
              </motion.div>
            ))}

            {/* Council Arbiter Card */}
            <motion.div
              initial={{ opacity: 0, y: 40 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-100px" }}
              transition={{ delay: 0.5, duration: 0.6, ease: "easeOut" }}
              whileHover={{ y: -8, scale: 1.02 }}
              className="p-8 rounded-3xl bg-gradient-to-br from-purple-900/30 to-black/60 backdrop-blur-3xl border border-purple-500/40 hover:border-purple-400/60 flex flex-col items-center text-center transition-all duration-300 shadow-[0_8px_32px_rgba(168,85,247,0.2)] hover:shadow-[0_8px_32px_rgba(168,85,247,0.4)] group relative overflow-hidden"
            >
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(168,85,247,0.15),transparent_50%)]" aria-hidden="true"></div>
              <div className="p-4 bg-purple-500/20 text-purple-300 rounded-2xl mb-6 shadow-[inset_0_0_20px_rgba(168,85,247,0.1)] border border-purple-500/30 relative z-10 group-hover:scale-110 transition-transform duration-500" aria-hidden="true">
                <ShieldCheck className="w-8 h-8" />
              </div>
              <h3 className="text-xl font-bold mb-2 text-white relative z-10 drop-shadow-[0_0_10px_rgba(168,85,247,0.5)]">Council Arbiter</h3>
              <span className="text-[11px] px-3 py-1 rounded-full bg-purple-900/50 text-purple-300 border border-purple-500/30 uppercase tracking-widest font-bold mb-4 relative z-10">Final Verdict</span>
              <p className="text-sm text-slate-300 leading-relaxed mb-6 font-normal relative z-10 flex-1">Cross-references all agent findings, resolves contradictions via tribunal, and produces the cryptographically signed forensic report.</p>
              <div className="w-full pt-4 border-t border-purple-500/20 relative z-10">
                <p className="text-xs text-purple-400/90 font-mono italic leading-relaxed">&quot;Synthesizing cross-modal evidence and resolving logical conflicts...&quot;</p>
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      {/* --- Footer ---  */}
      <footer className="relative z-10 py-10 border-t border-white/5 text-center px-6 bg-[#050505]">
        <p className="text-slate-500 text-sm font-light">
          Forensic Council is an academic project.
        </p>
      </footer>
    </div>
  );
}
