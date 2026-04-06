"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ShieldCheck, AlertTriangle, CheckCircle } from "lucide-react";
import { REPORT_TABS, TAB_ICONS } from "@/lib/constants";

interface MockAgent {
  name: string;
  verdict: string;
  conf: number;
  finding: string;
}

interface MockReport {
  file: string;
  verdict: string;
  verdictLabel: string;
  confidence: number;
  agents: MockAgent[];
  arbiterNote: string;
}

type ReportTab = (typeof REPORT_TABS)[number];

const MOCK_REPORTS: Record<ReportTab, MockReport> = {
  Image: {
    file: "crime_scene_photo.jpg",
    verdict: "MANIPULATED",
    verdictLabel: "Manipulation Detected",
    confidence: 94,
    agents: [
      { name: "Image Forensics", verdict: "SUSPICIOUS", conf: 96, finding: "ELA reveals compression artefacts inconsistent with original JPEG encoding. Copy-move detection flagged 3 duplicated regions." },
      { name: "Audio Forensics", verdict: "NOT_APPLICABLE", conf: 0, finding: "No audio stream present." },
      { name: "Metadata Expert", verdict: "AUTHENTIC", conf: 88, finding: "EXIF data consistent with claimed device. GPS coordinates match reported location." },
    ],
    arbiterNote: "Convergent signals from Image and Object agents confirm high-confidence manipulation. Audio and Video agents were inapplicable to this file type.",
  },
  Text: {
    file: "incident_report.pdf",
    verdict: "AUTHENTIC",
    verdictLabel: "Authentic",
    confidence: 87,
    agents: [
      { name: "Metadata Expert", verdict: "AUTHENTIC", conf: 91, finding: "PDF metadata timestamps are internally consistent. No sign of post-creation editing detected." },
      { name: "Image Forensics", verdict: "AUTHENTIC", conf: 83, finding: "Embedded images show no signs of manipulation." },
      { name: "Audio Forensics", verdict: "NOT_APPLICABLE", conf: 0, finding: "No audio content in document." },
    ],
    arbiterNote: "All applicable agents report authentic signals. Confidence is high but slight uncertainty remains due to limited cross-modal corroboration.",
  },
  Audio: {
    file: "witness_statement.wav",
    verdict: "SUSPICIOUS",
    verdictLabel: "Suspicious",
    confidence: 71,
    agents: [
      { name: "Audio Forensics", verdict: "SUSPICIOUS", conf: 74, finding: "Wav2Vec2 deepfake classifier flags synthetic voice probability at 68%. Spectral splice detected at 00:14.3." },
      { name: "Image Forensics", verdict: "NOT_APPLICABLE", conf: 0, finding: "No image content present." },
      { name: "Metadata Expert", verdict: "AUTHENTIC", conf: 88, finding: "Recording device fingerprint matches known microphone profile." },
    ],
    arbiterNote: "Audio agent detects moderate deepfake probability. Metadata is clean, creating minor conflict. Escalated to SUSPICIOUS pending deeper Wav2Vec2 analysis.",
  },
  Video: {
    file: "surveillance_clip.mp4",
    verdict: "MANIPULATED",
    verdictLabel: "Manipulation Detected",
    confidence: 98,
    agents: [
      { name: "Image Forensics", verdict: "SUSPICIOUS", conf: 91, finding: "Frame-level ELA detects inconsistent compression in facial regions across 47 frames." },
      { name: "Audio Forensics", verdict: "AUTHENTIC", conf: 89, finding: "Audio track shows no signs of splicing or synthesis." },
      { name: "Object Detection", verdict: "SUSPICIOUS", conf: 94, finding: "Lighting inconsistency detected: subject shadow direction contradicts ambient light source." },
    ],
    arbiterNote: "Image and Object agents deliver convergent high-confidence manipulation signals. Face-swap artefacts confirmed across temporal analysis. Verdict: MANIPULATED.",
  },
};

export function ExampleReportSection() {
  const [activeTab, setActiveTab] = useState(0);
  const tabKey = REPORT_TABS[activeTab];
  const report = MOCK_REPORTS[tabKey];

  const vcColor = (v: string) => {
    const u = v.toUpperCase();
    if (u.includes("MANIPULAT"))
      return {
        color: "#f43f5e",
        bg: "rgba(244,63,94,0.07)",
        border: "rgba(244,63,94,0.18)",
        Icon: AlertTriangle,
      };
    if (u.includes("AUTHENTIC"))
      return {
        color: "#34d399",
        bg: "rgba(52,211,153,0.07)",
        border: "rgba(52,211,153,0.18)",
        Icon: CheckCircle,
      };
    return {
      color: "#f59e0b",
      bg: "rgba(245,158,11,0.07)",
      border: "rgba(245,158,11,0.18)",
      Icon: AlertTriangle,
    };
  };
  const vc = vcColor(report.verdict);

  return (
    <div className="w-full max-w-4xl mx-auto">
      <div
        className="flex gap-2 mb-6 flex-wrap"
        role="tablist"
        aria-label="Example report types"
      >
        {REPORT_TABS.map((tab, i) => {
          const TabIcon = TAB_ICONS[tab];
          return (
            <motion.button
              key={tab}
              role="tab"
              id={`tab-${tab}`}
              aria-selected={activeTab === i}
              aria-controls={`panel-${tab}`}
              onClick={() => setActiveTab(i)}
              className="px-5 py-2 rounded-xl text-sm font-medium cursor-pointer flex items-center gap-2 border"
              style={
                activeTab === i
                  ? {
                      background: "rgba(34,211,238,0.1)",
                      borderColor: "rgba(34,211,238,0.25)",
                      color: "#22d3ee",
                    }
                  : {
                      background: "rgba(255,255,255,0.03)",
                      borderColor: "rgba(255,255,255,0.06)",
                      color: "rgba(255,255,255,0.4)",
                    }
              }
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
            >
              <TabIcon className="w-4 h-4" aria-hidden="true" /> {tab}
            </motion.button>
          );
        })}
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={activeTab}
          role="tabpanel"
          id={`panel-${tabKey}`}
          aria-labelledby={`tab-${tabKey}`}
          className="rounded-2xl overflow-hidden glass-panel"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.25 }}
        >
          <div className="px-6 py-4 border-b flex items-center justify-between border-white/[0.05]">
            <div className="flex items-center gap-2.5">
              <ShieldCheck
                className="w-4 h-4 text-cyan-400/50"
                aria-hidden="true"
              />
              <span className="text-xs font-mono tracking-widest text-white/30">
                FORENSIC COUNCIL
              </span>
            </div>
            <span className="text-xs font-mono text-white/[0.18]">
              DEMO &middot; MOCK DATA
            </span>
          </div>
          <div className="p-6 space-y-4">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div>
                <p className="text-[10px] font-mono uppercase tracking-widest mb-1 text-white/25">
                  Evidence File
                </p>
                <p className="text-sm font-mono text-white/75">{report.file}</p>
              </div>
              <div
                className="flex items-center gap-2 px-4 py-2 rounded-xl shrink-0"
                style={{ background: vc.bg, border: `1px solid ${vc.border}` }}
              >
                <vc.Icon
                  className="w-4 h-4"
                  style={{ color: vc.color }}
                  aria-hidden="true"
                />
                <span className="text-sm font-bold" style={{ color: vc.color }}>
                  {report.verdictLabel}
                </span>
                <span
                  className="text-sm font-mono font-bold"
                  style={{ color: vc.color }}
                >
                  {report.confidence}%
                </span>
              </div>
            </div>
            <div className="space-y-2">
              {report.agents.map((agent: MockAgent) => {
                const isNA = agent.verdict === "NOT_APPLICABLE";
                return (
                  <div
                    key={agent.name}
                    className="rounded-xl px-4 py-3 border"
                    style={{
                      background: isNA
                        ? "rgba(255,255,255,0.015)"
                        : "rgba(255,255,255,0.04)",
                      borderColor: isNA
                        ? "rgba(255,255,255,0.04)"
                        : "rgba(255,255,255,0.07)",
                      opacity: isNA ? 0.45 : 1,
                    }}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[11px] font-bold uppercase tracking-wide text-white/75">
                        {agent.name}
                      </span>
                      {!isNA ? (
                        <span
                          className="text-[10px] font-mono font-bold"
                          style={{
                            color:
                              agent.verdict === "AUTHENTIC"
                                ? "#34d399"
                                : agent.verdict === "SUSPICIOUS"
                                  ? "#f43f5e"
                                  : "#f59e0b",
                          }}
                        >
                          {agent.verdict} &middot; {agent.conf}%
                        </span>
                      ) : (
                        <span className="text-[9px] font-mono text-white/20">
                          N/A
                        </span>
                      )}
                    </div>
                    <p className="text-[13px] leading-relaxed text-white/50">
                      {agent.finding}
                    </p>
                  </div>
                );
              })}
            </div>
            <div className="pt-4 border-t border-white/[0.05]">
              <p className="text-[10px] font-mono uppercase tracking-widest mb-1.5 text-white/25">
                Arbiter Synthesis
              </p>
              <div className="p-4 rounded-xl bg-cyan-400/[0.03] border border-cyan-400/10">
                <p className="text-[13px] text-cyan-200/60 leading-relaxed italic">
                  &ldquo;{report.arbiterNote}&rdquo;
                </p>
              </div>
            </div>
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
