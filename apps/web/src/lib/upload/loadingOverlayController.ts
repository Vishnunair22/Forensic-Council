import { sessionOnlyStorage } from "@/lib/storage";
import { STORAGE_KEYS } from "@/lib/storageKeys";
import { MIN_DISPLAY_MS } from "@/lib/timings";

export class LoadingOverlayController {
  private visible = false;
  private text = "";
  private dispatchedCount = 0;
  private showTime = 0;
  private dismissTimer: ReturnType<typeof setTimeout> | null = null;
  private listeners: Set<(state: { visible: boolean; text: string; dispatchedCount: number }) => void> = new Set();

  getState() {
    return { visible: this.visible, text: this.text, dispatchedCount: this.dispatchedCount };
  }

  subscribe(listener: (state: { visible: boolean; text: string; dispatchedCount: number }) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  show(text?: string): void {
    this.visible = true;
    this.showTime = Date.now();
    this.text = text || "Initializing workspace";
    this.syncStorage();
    this.notify();
  }

  updateText(text: string): void {
    this.text = text;
    sessionOnlyStorage.setItem(STORAGE_KEYS.FC_LOADING_TEXT, text);
    this.notify();
  }

  updateDispatchedCount(count: number): void {
    this.dispatchedCount = count;
    sessionOnlyStorage.setItem(STORAGE_KEYS.FC_LOADING_DISPATCHED, String(count));
    this.notify();
  }

  dismiss(): void {
    this.clearTimer();
    const elapsed = Date.now() - this.showTime;
    if (elapsed < MIN_DISPLAY_MS) {
      this.dismissTimer = setTimeout(() => this.forceDismiss(), MIN_DISPLAY_MS - elapsed);
    } else {
      this.forceDismiss();
    }
  }

  forceDismiss(): void {
    this.clearTimer();
    this.visible = false;
    this.text = "";
    this.dispatchedCount = 0;
    this.clearStorage();
    this.notify();
  }

  private clearTimer(): void {
    if (this.dismissTimer) {
      clearTimeout(this.dismissTimer);
      this.dismissTimer = null;
    }
  }

  private syncStorage(): void {
    sessionOnlyStorage.setItem(STORAGE_KEYS.FC_SHOW_LOADING, "true");
    sessionOnlyStorage.setItem(STORAGE_KEYS.FC_LOADING_TEXT, this.text);
    sessionOnlyStorage.setItem(STORAGE_KEYS.FC_LOADING_DISPATCHED, String(this.dispatchedCount));
  }

  private clearStorage(): void {
    sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
    sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_LOADING_TEXT);
    sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_LOADING_DISPATCHED);
  }

  private notify(): void {
    this.listeners.forEach((fn) => fn(this.getState()));
  }
}

export const loadingOverlayController = new LoadingOverlayController();
