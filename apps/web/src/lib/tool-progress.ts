import {
  Activity,
  AudioWaveform,
  Brain,
  Camera,
  Clock,
  Database,
  FileSearch,
  Fingerprint,
  Gauge,
  ImageIcon,
  Layers,
  Scan,
  Search,
  Shield,
  Speaker,
  Video,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { getToolIcon } from "./tool-icons";

type ProgressDescriptor = {
  label: string;
  icon: LucideIcon;
};

export const AGENT_PREFIXES: Record<string, string> = {
  Agent1: "Graphic",
  Agent2: "Acoustic",
  Agent3: "Scene",
  Agent4: "Motion",
  Agent5: "Digital",
};

export function getAgentPrefix(agentId: string): string {
  return AGENT_PREFIXES[agentId] || "Node";
}

const DEFAULT_TOTALS: Record<string, number> = {
  Agent1: 6,
  Agent2: 5,
  Agent3: 5,
  Agent4: 6,
  Agent5: 6,
};

const TOOL_PROGRESS: Record<string, ProgressDescriptor> = {
  extract_text_from_image: { label: "Identifying the image contents using ocr tools", icon: Camera },
  extract_evidence_text: { label: "Identifying the image contents using ocr tools", icon: Camera },
  object_text_ocr: { label: "Identifying the image contents using ocr tools", icon: Camera },
  analyze_image_content: { label: "Classifying visual elements and content", icon: ImageIcon },
  ela_full_image: { label: "Analyzing image compression for anomalies", icon: Scan },
  ela_anomaly_classify: { label: "Classifying detected anomaly regions", icon: Scan },
  jpeg_ghost_detect: { label: "Detecting JPEG recompression signatures", icon: Layers },
  frequency_domain_analysis: { label: "Inspecting spectral frequency artifacts", icon: Activity },
  deepfake_frequency_check: { label: "Checking synthetic-media frequency traces", icon: Brain },
  noise_fingerprint: { label: "Comparing camera noise consistency", icon: Fingerprint },
  prnu_analysis: { label: "Comparing sensor fingerprint consistency", icon: Fingerprint },
  copy_move_detect: { label: "Searching for cloned image regions", icon: Layers },
  splicing_detect: { label: "Detecting image splice boundaries", icon: Layers },
  image_splice_check: { label: "Validating image splice indicators", icon: Layers },
  file_hash_verify: { label: "Verifying cryptographic file hash", icon: Shield },
  adversarial_robustness_check: { label: "Testing for anti-forensic patterns", icon: Shield },
  object_detection: { label: "Identifying objects and scene elements", icon: Search },
  scene_incongruence: { label: "Checking scene consistency", icon: Search },
  lighting_consistency: { label: "Comparing lighting and shadow direction", icon: Zap },
  scale_validation: { label: "Checking object scale and proportions", icon: Gauge },
  secondary_classification: { label: "Cross-checking object labels", icon: Search },
  contraband_database: { label: "Screening objects against risk database", icon: Database },
  vector_contraband_search: { label: "Searching visual risk embeddings", icon: Database },
  speaker_diarize: { label: "Separating speakers in the audio", icon: Speaker },
  anti_spoofing_detect: { label: "Checking for spoofed speech", icon: Speaker },
  voice_clone_detect: { label: "Checking for cloned voice signatures", icon: Speaker },
  prosody_analyze: { label: "Measuring speech rhythm and stress", icon: AudioWaveform },
  audio_splice_detect: { label: "Scanning audio splice points", icon: AudioWaveform },
  background_noise_analysis: { label: "Comparing background noise consistency", icon: AudioWaveform },
  codec_fingerprinting: { label: "Checking audio codec history", icon: AudioWaveform },
  enf_analysis: { label: "Comparing electrical grid frequency", icon: AudioWaveform },
  audio_visual_sync: { label: "Checking audio and video sync", icon: Video },
  av_file_identity: { label: "Reading media container identity", icon: Video },
  mediainfo_profile: { label: "Profiling codec and container metadata", icon: Video },
  optical_flow_analysis: { label: "Tracking frame-to-frame motion", icon: Video },
  optical_flow_analyze: { label: "Tracking frame-to-frame motion", icon: Video },
  frame_consistency_analysis: { label: "Comparing frame consistency", icon: Video },
  vfi_error_map: { label: "Checking generated-frame artifacts", icon: Video },
  interframe_forgery_detector: { label: "Scanning temporal forgery traces", icon: Video },
  face_swap_detection: { label: "Checking face-swap signatures", icon: Camera },
  rolling_shutter_validation: { label: "Validating rolling-shutter motion", icon: Video },
  thumbnail_coherence: { label: "Comparing embedded thumbnails", icon: ImageIcon },
  video_metadata: { label: "Reading video metadata", icon: FileSearch },
  exif_extract: { label: "Extracting camera metadata", icon: FileSearch },
  extract_deep_metadata: { label: "Reading extended metadata", icon: FileSearch },
  metadata_anomaly_score: { label: "Scoring metadata consistency", icon: Database },
  metadata_anomaly_scorer: { label: "Scoring metadata consistency", icon: Database },
  exif_isolation_forest: { label: "Checking metadata fabrication patterns", icon: Database },
  gps_timezone_validate: { label: "Comparing GPS and timestamp timezone", icon: Clock },
  timestamp_analysis: { label: "Auditing timestamp consistency", icon: Clock },
  astronomical_api: { label: "Checking sun position against metadata", icon: Clock },
  astro_grounding: { label: "Checking sun position against metadata", icon: Clock },
  steganography_scan: { label: "Scanning for hidden embedded data", icon: Layers },
  file_structure_analysis: { label: "Inspecting file structure integrity", icon: Layers },
  hex_signature_scan: { label: "Scanning binary editor signatures", icon: FileSearch },
  c2pa_verify: { label: "Checking content credentials", icon: Shield },
  provenance_chain_verify: { label: "Checking provenance chain", icon: Shield },
  camera_profile_match: { label: "Comparing camera profile consistency", icon: Fingerprint },
  gemini_deep_forensic: { label: "Synthesizing cross-tool evidence", icon: Brain },

  // Short-form aliases emitted by some backend tool_name values
  ocr:        { label: "Identifying image contents using OCR tools",  icon: Camera },
  ela:        { label: "Detecting compression anomalies (ELA)",       icon: Scan },
  noise:      { label: "Profiling sensor-noise residuals",            icon: Fingerprint },
  splicing:   { label: "Searching for spliced regions",               icon: Layers },
  exif:       { label: "Reading EXIF / container metadata",           icon: FileSearch },
  c2pa:       { label: "Validating C2PA provenance chain",            icon: Shield },
  yolo:       { label: "Detecting objects and scene context",         icon: Search },
  diariz:     { label: "Diarising speakers in audio",                 icon: Speaker },
  spectro:    { label: "Analysing audio spectrogram",                 icon: AudioWaveform },
  frame_diff: { label: "Comparing frames for tampering",              icon: Video },
};

const FALLBACK_BY_AGENT: Record<string, ProgressDescriptor[]> = {
  Agent1: [
    { label: "Identifying visual content and elements", icon: ImageIcon },
    { label: "Identifying the image contents using ocr tools", icon: Camera },
    { label: "Analyzing image compression for anomalies", icon: Scan },
    { label: "Inspecting spectral frequency artifacts", icon: Activity },
    { label: "Validating camera noise consistency", icon: Fingerprint },
    { label: "Synthesizing visual evidence", icon: Brain },
  ],
  Agent2: [
    { label: "Separating speakers in the audio", icon: Speaker },
    { label: "Checking for spoofed speech", icon: Speaker },
    { label: "Measuring speech rhythm and stress", icon: AudioWaveform },
    { label: "Scanning audio splice points", icon: AudioWaveform },
    { label: "Profiling codec history", icon: Activity },
  ],
  Agent3: [
    { label: "Detecting objects and scene elements", icon: Search },
    { label: "Checking scene consistency", icon: Search },
    { label: "Comparing lighting and shadow direction", icon: Zap },
    { label: "Checking object scale and proportions", icon: Gauge },
    { label: "Synthesizing scene evidence", icon: Brain },
  ],
  Agent4: [
    { label: "Reading media container identity", icon: Video },
    { label: "Tracking frame-to-frame motion", icon: Video },
    { label: "Comparing frame consistency", icon: Layers },
    { label: "Checking face-swap signatures", icon: Camera },
    { label: "Inspecting temporal forgery traces", icon: Activity },
    { label: "Synthesizing video evidence", icon: Brain },
  ],
  Agent5: [
    { label: "Extracting camera metadata", icon: FileSearch },
    { label: "Scoring metadata consistency", icon: Database },
    { label: "Comparing GPS and timestamp timezone", icon: Clock },
    { label: "Auditing timestamp consistency", icon: Clock },
    { label: "Scanning binary signatures", icon: Layers },
    { label: "Checking provenance chain", icon: Shield },
  ],
};

function normalizeToolName(raw?: string | null): string {
  return String(raw || "")
    .trim()
    .replace(/^Calling\s+/i, "")
    .replace(/\.\.\.$/, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_|_$/g, "");
}

export function getDefaultProgressTotal(agentId: string): number {
  return DEFAULT_TOTALS[agentId] || 6;
}

export function getLiveProgressDescriptor(
  agentId: string,
  toolName?: string | null,
  stepIndex = 0,
): ProgressDescriptor {
  const normalized = normalizeToolName(toolName);
  if (normalized && TOOL_PROGRESS[normalized]) return TOOL_PROGRESS[normalized];
  if (normalized) {
    const icon = getToolIcon(normalized);
    return {
      label: `Executing forensic tool: ${toolName || normalized}`,
      icon,
    };
  }

  const fallbacks = FALLBACK_BY_AGENT[agentId] || FALLBACK_BY_AGENT.Agent1;
  return fallbacks[Math.max(0, stepIndex) % fallbacks.length];
}
