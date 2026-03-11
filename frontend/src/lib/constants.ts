export type AgentDefinition = {
    id: string;
    name: string;
    role: string;
    desc: string;
    simulation: {
        result: string;
        confidence: number;
        thinking: string;
        thinkingPhrases: string[]; // Dynamic sub-tasks
    }
};

export const AGENTS_DATA: AgentDefinition[] = [
    {
        id: "Agent1",
        name: "Image Integrity Expert",
        role: "Image Integrity",
        desc: "Detects manipulation, splicing, compositing, and anti-forensics evasion at the pixel level.",
        simulation: {
            result: "Noise distribution consistent with ISO 3200 sensor profile.",
            confidence: 99,
            thinking: "Analyzing sensor pattern noise (PRNU)...",
            thinkingPhrases: ["Checking error level analysis...", "Verifying quantization tables...", "Scanning for copy-move cloning..."]
        }
    },
    {
        id: "Agent2",
        name: "Audio Forensics Expert",
        role: "Audio & Multimedia",
        desc: "Detects audio deepfakes, splices, re-encoding events, and audio-visual sync breaks.",
        simulation: {
            result: "Audio track shows consistent prosody. No codec mismatch detected.",
            confidence: 96,
            thinking: "Running speaker diarization...",
            thinkingPhrases: ["Checking anti-spoofing markers...", "Analyzing background noise consistency...", "Verifying A/V sync..."]
        }
    },
    {
        id: "Agent3",
        name: "Object & Weapon Analyst",
        role: "Object & Weapon",
        desc: "Detects and contextually validates objects, weapons, and lighting anomalies.",
        simulation: {
            result: "Identified: Civilian Vehicle (Type A), Structure B (Residential).",
            confidence: 94,
            thinking: "Running YOLOv8 inference grid...",
            thinkingPhrases: ["Classifying obscure shapes...", "Checking against contraband DB...", "Validating scene lighting..."]
        }
    },
    {
        id: "Agent4",
        name: "Temporal Video Analyst",
        role: "Temporal Video",
        desc: "Detects frame-level edit points, deepfake face swaps, and optical flow anomalies.",
        simulation: {
            result: "Frame interval 33ms stable. Motion vectors align with camera track.",
            confidence: 98,
            thinking: "Mapping frame-to-frame pixel displacement...",
            thinkingPhrases: ["Analyzing optical flow...", "Detecting face-swapping artifacts...", "Checking rolling shutter behavior..."]
        }
    },
    {
        id: "Agent5",
        name: "Metadata & Context Expert",
        role: "Metadata & Context",
        desc: "Analyzes EXIF data, GPS-timestamp consistency, and detects provenance fabrication.",
        simulation: {
            result: "GPS: 34.05°N, 118.24°W. Timestamp verified against solar positioning.",
            confidence: 99,
            thinking: "Cross-referencing satellite telemetry...",
            thinkingPhrases: ["Parsing EXIF/XMP tags...", "Verifying device signature...", "Running reverse image search..."]
        }
    }
];

// Computed helpers for backward compatibility if needed, or direct usage
export const MOCK_AGENTS = AGENTS_DATA.map(a => ({ name: a.name, role: a.role, desc: a.desc }));

export const ALLOWED_MIME_TYPES = new Set([
    "image/jpeg", "image/png", "image/tiff", "image/webp", "image/gif", "image/bmp",
    "video/mp4", "video/quicktime", "video/x-msvideo",
    "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp4", "audio/flac",
]);
