import { autoLoginAsInvestigator } from "@/lib/api";
import { storage } from "@/lib/storage";
import { STORAGE_KEYS } from "@/lib/storageKeys";

export type AuthStatus = "IDLE" | "PENDING" | "AUTHENTICATED" | "FAILED";

export class AuthService {
  private status: AuthStatus = "IDLE";
  private promise: Promise<void> | null = null;
  private error: Error | null = null;
  private listeners: Set<(status: AuthStatus, error?: string) => void> = new Set();

  getStatus(): AuthStatus {
    return this.status;
  }

  getError(): Error | null {
    return this.error;
  }

  subscribe(listener: (status: AuthStatus, error?: string) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  async ensureAuthenticated(): Promise<void> {
    if (this.status === "AUTHENTICATED") return;
    if (this.promise) return this.promise;

    this.setStatus("PENDING");
    this.promise = autoLoginAsInvestigator()
      .then(() => {
        storage.setItem(STORAGE_KEYS.AUTH_OK, "1");
        this.error = null;
        this.setStatus("AUTHENTICATED");
      })
      .catch((err: unknown) => {
        this.error = err instanceof Error ? err : new Error("Authentication failed");
        this.promise = null;
        this.setStatus("FAILED", this.error.message);
        throw this.error;
      });

    return this.promise;
  }

  reset(): void {
    this.promise = null;
    this.error = null;
    this.setStatus("IDLE");
  }

  private setStatus(status: AuthStatus, error?: string): void {
    this.status = status;
    this.listeners.forEach((fn) => fn(status, error));
  }
}

export const authService = new AuthService();
