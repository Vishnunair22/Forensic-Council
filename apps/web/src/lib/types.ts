export interface HistoryItem {
  sessionId: string;
  fileName: string;
  verdict: string;
  confidence?: number; // 0–1 float
  timestamp: number;
  type: "Initial" | "Deep" | string;
  thumbnail?: string;
  mime?: string;
}

export interface Finding {
  finding_type?: string;
  metadata?: Record<string, unknown> | null;
}
