export interface HistoryItem {
  sessionId: string;
  fileName: string;
  verdict: string;
  timestamp: number;
  type: "Initial" | "Deep" | string;
  thumbnail?: string;
  mime?: string;
}

export interface Finding {
  finding_type?: string;
  metadata?: Record<string, unknown> | null;
}
