"use client";

import { 
  ArrowRight, ShieldCheck, Microscope, 
  UploadCloud, Cpu, Award, 
  Scale, FileSearch, Bug, Globe, ScrollText, Network 
} from "lucide-react";
import { useRouter } from "next/navigation";
import { GlobalFooter } from "@/components/ui/GlobalFooter";
import { startInvestigation } from "@/lib/api";
import { useState, useRef, useEffect } from "react";

const AGENTS = [
  { name: "Arbiter", role: "The Judge / Coordinator", icon: Scale, color: "text-amber-400", bg: "bg-amber-400/10", border: "border-amber-400/20" },
  { name: "Forensics", role: "File & Hex Analysis", icon: FileSearch, color: "text-cyan-400", bg: "bg-cyan-400/10", border: "border-cyan-400/20" },
  { name: "Malware", role: "Payload Detection", icon: Bug, color: "text-red-400", bg: "bg-red-400/10", border: "border-red-400/20" },
  { name: "Threat Intel", role: "OSINT & Signatures", icon: Globe, color: "text-emerald-400", bg: "bg-emerald-400/10", border: "border-emerald-400/20" },
  { name: "Logs", role: "Timeline Reconstruction", icon: ScrollText, color: "text-blue-400", bg: "bg-blue-400/10", border: "border-blue-400/20" },
  { name: "Context", role: "Motive & Pattern Analysis", icon: Network, color: "text-purple-400", bg: "bg-purple-400/10", border: "border-purple-400/20" },
];

const STAGES = [
  { title: "1. Upload & Intake", desc: "Submit digital evidence securely.", icon: UploadCloud },
  { title: "2. Multi-Agent Analysis", desc: "Autonomous specialists investigate in parallel.", icon: Cpu },
  { title: "3. Cryptographic Verdict", desc: "Final consensus with undeniable proof.", icon: Award },
];

export default function LandingPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [scrollY, setScrollY] = useState(0);

  useEffect(() => {
    sessionStorage.removeItem("forensic_auto_start");
    
    const handleScroll = () => {
      setScrollY(window.scrollY);
    };
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const handleInitiate = async () => {
    if (!file || isSubmitting) return;
    setIsSubmitting(true);
    
    const caseId = "CASE-" + Date.now();
    const investigatorId = "REQ-123456";
    sessionStorage.setItem("forensic_case_id", caseId);
    sessionStorage.setItem("forensic_investigator_id", investigatorId);
    sessionStorage.setItem("forensic_auto_start", "true");
    
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const w = window as any;
    w.__forensic_pending_file = file;
    w.__forensic_investigation_promise = startInvestigation(file, caseId, investigatorId);
    
    router.push("/evidence");
  };

  // 3D Parallax Calculation for Background Microscope
  const microscopeTransform = `
    perspective(1000px) 
    rotateX(${scrollY * 0.05}deg) 
    rotateY(${scrollY * 0.02}deg) 
    translateZ(${scrollY * 0.5}px)
    translateY(${scrollY * 0.2}px)
  `;

  return (
    <div className="relative min-h-screen bg-black text-white flex flex-col font-sans selection:bg-[#00f0ff]/30 overflow-x-hidden">
      
      {/* Top Navbar */}
      <header className="fixed top-0 w-full p-6 flex items-center justify-between z-50 bg-black/40 backdrop-blur-md border-b border-white/5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[#00f0ff]/10 border border-[#00f0ff]/30 flex items-center justify-center text-[#00f0ff] font-bold tracking-widest text-xs shadow-[0_0_15px_rgba(0,240,255,0.2)]">
            FC
          </div>
          <span className="font-bold uppercase tracking-[0.2em] text-sm text-white/90">Forensic Council</span>
        </div>
        <div className="flex items-center gap-2 text-[10px] font-mono text-white/40 uppercase tracking-[0.2em] font-bold">
          <div className="w-2 h-2 rounded-full bg-[#00f0ff] shadow-[0_0_10px_rgba(0,240,255,0.8)]" style={{ animation: "spin-slow 3s infinite alternate" }} />
          System Online
        </div>
      </header>

      {/* Main Content Wrapper */}
      <main className="flex-1 flex flex-col items-center relative z-10 pt-32 pb-16 px-6 no-scrollbar">
        
        {/* === HERO SECTION === */}
        <section className="w-full max-w-5xl flex flex-col items-center justify-center text-center space-y-8 min-h-[70vh]">
          <div className="inline-flex items-center gap-3 px-5 py-2.5 rounded-full border border-[#00f0ff]/20 bg-[#00f0ff]/5 text-[#00f0ff] text-xs font-bold uppercase tracking-[0.3em] backdrop-blur-md shadow-[0_0_20px_rgba(0,240,255,0.1)]">
            <ShieldCheck className="w-4 h-4" />
            Decentralized Intelligence
          </div>

          <h1 className="text-4xl md:text-5xl lg:text-6xl font-black tracking-tighter leading-[1.1] text-transparent bg-clip-text bg-gradient-to-br from-white via-white to-white/40 drop-shadow-2xl">
            Multi-Agent <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-[#00f0ff] to-[#818cf8] filter drop-shadow-[0_0_15px_rgba(0,240,255,0.4)]">
              Forensic Evidence <br className="md:hidden" /> Analysis System
            </span>
          </h1>

          <p className="max-w-2xl mx-auto text-lg md:text-xl text-white/60 leading-relaxed font-light">
            Autonomous specialist agents independently audit digital evidence, resolve artifacts, and synthesize objective forensic verdicts with cryptographic certainty.
          </p>

          {/* Upload Module / CTA */}
          <div className="glass-ethereal w-full max-w-xl mx-auto p-8 rounded-3xl space-y-6 mt-12 transition-all hover:-translate-y-2 duration-500 hover:shadow-[0_0_40px_rgba(0,240,255,0.15)] relative overflow-hidden group">
            
            {/* Inner Glare Effect */}
            <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />

            <div className="flex flex-col items-center gap-4 text-center relative z-10">
              <div className="w-16 h-16 rounded-2xl bg-[#00f0ff]/10 border border-[#00f0ff]/20 flex items-center justify-center text-[#00f0ff] shadow-[0_0_20px_rgba(0,240,255,0.2)]">
                 <Microscope className="w-8 h-8" strokeWidth={1.5} />
              </div>
              <div>
                <h3 className="text-xl font-bold text-white tracking-wide">Initiate Analysis</h3>
                <p className="text-sm text-white/40 mt-1 font-medium">Select an image, video, or audio artifact.</p>
              </div>
            </div>

            <div 
              className="relative z-10 border-2 border-dashed border-[#00f0ff]/20 rounded-2xl p-6 text-center bg-[#00f0ff]/5 hover:bg-[#00f0ff]/10 hover:border-[#00f0ff]/40 transition-all duration-300 cursor-pointer group/drop"
              onClick={() => fileInputRef.current?.click()}
            >
              <input 
                ref={fileInputRef}
                type="file" 
                className="hidden"
                accept="image/*,video/*,audio/*"
                onChange={(e) => setFile(e.target.files?.[0] || null)} 
              />
              <p className="text-sm font-bold text-[#00f0ff] uppercase tracking-widest group-hover/drop:scale-105 transition-transform duration-300">
                {file ? file.name : "Browse Files"}
              </p>
              <p className="text-[10px] font-mono text-white/40 mt-2 uppercase tracking-wide">Max size 50MB</p>
            </div>
            
            <button 
              onClick={handleInitiate}
              disabled={!file || isSubmitting}
              className="relative w-full inline-flex items-center justify-center gap-2 px-8 py-4 rounded-full font-bold uppercase tracking-[0.15em] text-sm overflow-hidden group/btn disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-300 text-white shadow-[0_0_20px_rgba(0,240,255,0.2)] hover:shadow-[0_0_40px_rgba(0,240,255,0.4)] disabled:shadow-none"
            >
              <div className="absolute inset-0 bg-gradient-to-r from-[#0891b2] via-[#06b6d4] to-[#00f0ff] opacity-90 group-hover/btn:opacity-100 transition-opacity" />
              <div className="absolute inset-0 opacity-0 group-hover/btn:opacity-20 transition-opacity bg-[radial-gradient(circle_at_center,white_0%,transparent_100%)] mix-blend-overlay" />
              <span className="relative z-10 flex items-center">
                {isSubmitting ? "Initializing Sequence..." : "Start Investigation"}
                <ArrowRight className="w-4 h-4 ml-2 transition-transform group-hover/btn:translate-x-1" />
              </span>
            </button>
          </div>
        </section>

        {/* === HOW IT WORKS SECTION === */}
        <section className="w-full max-w-6xl mt-32 space-y-12">
          <div className="text-center space-y-4">
            <h2 className="text-3xl md:text-4xl font-black tracking-tight text-white">
              Operational <span className="text-[#00f0ff]">Protocol</span>
            </h2>
            <p className="text-white/40 uppercase tracking-widest text-xs font-mono">Standard Operating Procedure</p>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {STAGES.map((stage, idx) => (
              <div key={idx} className="glass-ethereal p-8 rounded-3xl flex flex-col items-center text-center space-y-6 hover:bg-white/[0.04] transition-colors">
                <div className="w-16 h-16 rounded-full bg-white/5 border border-white/10 flex items-center justify-center text-white/80 shadow-inner">
                  <stage.icon className="w-8 h-8" strokeWidth={1.5} />
                </div>
                <div>
                  <h4 className="text-lg font-bold text-white mb-2">{stage.title}</h4>
                  <p className="text-sm text-white/50 leading-relaxed font-light">{stage.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* === MEET THE AGENTS SECTION === */}
        <section className="w-full max-w-6xl mt-32 space-y-12 mb-20">
          <div className="text-center space-y-4">
            <h2 className="text-3xl md:text-4xl font-black tracking-tight text-white">
              Meet The <span className="text-[#00f0ff]">Agents</span>
            </h2>
            <p className="text-white/40 uppercase tracking-widest text-xs font-mono">Specialized Intelligence Units</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {AGENTS.map((agent, idx) => (
              <div key={idx} className="surface-panel hover:surface-panel-high p-6 rounded-3xl flex items-start gap-5 transition-all duration-300 hover:-translate-y-1 group">
                <div className={`w-14 h-14 rounded-2xl ${agent.bg} border ${agent.border} flex items-center justify-center shrink-0 transition-transform group-hover:scale-110 duration-300`}>
                  <agent.icon className={`w-6 h-6 ${agent.color}`} strokeWidth={1.5} />
                </div>
                <div className="flex flex-col justify-center h-14">
                  <h4 className="text-base font-bold text-white tracking-wide">{agent.name}</h4>
                  <p className="text-xs text-white/40 uppercase tracking-wider font-mono mt-1">{agent.role}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

      </main>

      <GlobalFooter />
      
      <style jsx global>{`
        @keyframes scan {
          0% { top: 0%; opacity: 0; }
          10% { opacity: 1; }
          90% { opacity: 1; }
          100% { top: 100%; opacity: 0; }
        }
        .no-scrollbar::-webkit-scrollbar {
          display: none;
        }
        .no-scrollbar {
          -ms-overflow-style: none;
          scrollbar-width: none;
        }
      `}</style>
    </div>
  );
}
