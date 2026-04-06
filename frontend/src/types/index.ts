export const VERDICTS = [
  "AUTHENTIC",
  "SUSPICIOUS",
  "MANIPULATED",
  "NOT_APPLICABLE",
  "INCONCLUSIVE",
] as const;

export type Verdict = (typeof VERDICTS)[number];

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
