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
