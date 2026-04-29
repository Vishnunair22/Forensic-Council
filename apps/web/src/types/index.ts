export const VERDICTS = [
  "AUTHENTIC",
  "LIKELY_AUTHENTIC",
  "INCONCLUSIVE",
  "SUSPICIOUS",
  "LIKELY_MANIPULATED",
  "MANIPULATED",
  "ABSTAIN",
  "NOT_APPLICABLE",
] as const;

export type Verdict = (typeof VERDICTS)[number];

export interface HistoryItem {
  sessionId: string;
  fileName: string;
  verdict: string;
  timestamp: number;
  type: "Initial" | "Deep";
  thumbnail?: string;
  mime?: string;
  score?: number;
  analysisTime?: string;
}

export type AgentResult = {
  id: string;
  name: string;
  role: string;
  result: string;
  confidence: number;
  thinking?: string;
  metadata?: Record<string, unknown>;
};

export type Report = {
  id: string;
  fileName: string;
  timestamp: string;
  summary: string;
  agents: AgentResult[];
  verdict: Verdict;
};
