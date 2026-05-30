export type UploadEvent =
  | { type: "START_AUTH" }
  | { type: "AUTH_SUCCESS" }
  | { type: "AUTH_FAILED"; error: string }
  | { type: "FILE_SELECTED"; file: File }
  | { type: "FILE_REJECTED"; error: string }
  | { type: "START_UPLOAD" }
  | { type: "UPLOAD_PROGRESS"; progress: number }
  | { type: "UPLOAD_COMPLETE"; sessionId: string }
  | { type: "UPLOAD_FAILED"; error: string }
  | { type: "WS_CONNECTED" }
  | { type: "WS_FAILED"; error: string }
  | { type: "ANALYSIS_READY" }
  | { type: "ERROR"; error: string }
  | { type: "RESET" };

export type UploadStage =
  | { stage: "IDLE" }
  | { stage: "AUTH_PENDING" }
  | { stage: "AUTH_FAILED"; error: string }
  | { stage: "AUTHENTICATED" }
  | { stage: "FILE_SELECTED"; file: File }
  | { stage: "FILE_REJECTED"; error: string }
  | { stage: "UPLOADING"; file: File; progress: number }
  | { stage: "WS_CONNECTING"; sessionId: string }
  | { stage: "ANALYZING"; sessionId: string }
  | { stage: "ERROR"; error: string }
  | { stage: "COMPLETE"; sessionId: string };

const STORAGE_KEY = "fc_upload_state";

export class UploadStateMachine {
  private state: UploadStage = { stage: "IDLE" };
  private listeners: Set<(state: UploadStage) => void> = new Set();

  constructor() {
    this.restore();
  }

  getState(): UploadStage {
    return this.state;
  }

  transition(event: UploadEvent): UploadStage {
    const next = this.reduce(this.state, event);
    if (next !== this.state) {
      this.state = next;
      this.persist();
      this.notify();
    }
    return this.state;
  }

  subscribe(listener: (state: UploadStage) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  reset(): void {
    this.state = { stage: "IDLE" };
    this.persist();
    this.notify();
  }

  private reduce(state: UploadStage, event: UploadEvent): UploadStage {
    switch (state.stage) {
      case "IDLE":
        if (event.type === "START_AUTH") return { stage: "AUTH_PENDING" };
        if (event.type === "FILE_SELECTED") return { stage: "FILE_SELECTED", file: event.file };
        return state;
      case "AUTH_PENDING":
        if (event.type === "AUTH_SUCCESS") return { stage: "AUTHENTICATED" };
        if (event.type === "AUTH_FAILED") return { stage: "AUTH_FAILED", error: event.error };
        if (event.type === "FILE_SELECTED") return { stage: "FILE_SELECTED", file: event.file };
        return state;
      case "AUTH_FAILED":
        if (event.type === "START_AUTH") return { stage: "AUTH_PENDING" };
        if (event.type === "FILE_SELECTED") return { stage: "FILE_SELECTED", file: event.file };
        return state;
      case "AUTHENTICATED":
        if (event.type === "FILE_SELECTED") return { stage: "FILE_SELECTED", file: event.file };
        return state;
      case "FILE_SELECTED":
        if (event.type === "FILE_REJECTED") return { stage: "FILE_REJECTED", error: event.error };
        if (event.type === "START_UPLOAD") return { stage: "UPLOADING", file: state.file, progress: 0 };
        if (event.type === "ERROR") return { stage: "ERROR", error: event.error };
        return state;
      case "FILE_REJECTED":
        if (event.type === "FILE_SELECTED") return { stage: "FILE_SELECTED", file: event.file };
        return state;
      case "UPLOADING":
        if (event.type === "UPLOAD_PROGRESS") return { ...state, progress: event.progress };
        if (event.type === "UPLOAD_COMPLETE") return { stage: "WS_CONNECTING", sessionId: event.sessionId };
        if (event.type === "UPLOAD_FAILED") return { stage: "ERROR", error: event.error };
        return state;
      case "WS_CONNECTING":
        if (event.type === "WS_CONNECTED") return { stage: "ANALYZING", sessionId: state.sessionId };
        if (event.type === "WS_FAILED") return { stage: "ERROR", error: event.error };
        return state;
      case "ANALYZING":
        if (event.type === "ANALYSIS_READY") return { stage: "COMPLETE", sessionId: state.sessionId };
        if (event.type === "ERROR") return { stage: "ERROR", error: event.error };
        return state;
      case "ERROR":
        if (event.type === "FILE_SELECTED") return { stage: "FILE_SELECTED", file: event.file };
        return state;
      case "COMPLETE":
        return state;
    }
  }

  private persist(): void {
    if (typeof window === "undefined") return;
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(this.state));
    } catch {
      /* ephemeral state — non-critical */
    }
  }

  private restore(): void {
    if (typeof window === "undefined") return;
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as UploadStage;
        if (parsed && "stage" in parsed) {
          this.state = parsed;
        }
      }
    } catch {
      sessionStorage.removeItem(STORAGE_KEY);
    }
  }

  private notify(): void {
    this.listeners.forEach((fn) => fn(this.state));
  }
}

export const uploadStateMachine = new UploadStateMachine();
