/**
 * Forensic Council — API Utilities
 */

const _TOKEN_KEY = "forensic_auth_token";
const _TOKEN_EXPIRY_KEY = "forensic_auth_token_expiry";

export const isDev = process.env.NODE_ENV !== "production";

export const dbg = {
  log: isDev ? console.log.bind(console) : () => {},
  warn: isDev ? console.warn.bind(console) : () => {},
  error: isDev ? console.error.bind(console) : () => {},
};

// ── Origin & URLs ─────────────────────────────────────────────────────────────

export const API_BASE =
  typeof window === "undefined"
    ? process.env.INTERNAL_API_URL || "http://localhost:8000"
    : "";

export const WS_BASE =
  typeof window !== "undefined"
    ? (() => {
        if (process.env.NEXT_PUBLIC_WS_URL) return process.env.NEXT_PUBLIC_WS_URL;
        const { protocol, host } = window.location;
        const wsProto = protocol === "https:" ? "wss" : "ws";
        
        // Handle Next.js dev server proxying fallback
        if (host.includes(":3000")) {
          return `${wsProto}://${host.replace(":3000", ":8000")}`;
        }
        return `${wsProto}://${host}`;
      })()
    : (() => {
        const base = process.env.INTERNAL_API_URL || "http://localhost:8000";
        return base.replace(/^https?/, (m) => (m === "https" ? "wss" : "ws"));
      })();

// ── Cookie & Auth Helpers ────────────────────────────────────────────────────

export function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(
    new RegExp(`(?:^|; )${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}=([^;]*)`),
  );
  return match ? decodeURIComponent(match[1]) : null;
}

export async function ensureCsrfToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;
  const token = readCookie("csrf_token");
  if (token) return token;

  try {
    await fetch(`${API_BASE}/api/v1/health`, {
      method: "GET",
      credentials: "include",
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    // Busy wait for cookie persistence
    for (let i = 0; i < 20; i++) {
        const t = readCookie("csrf_token");
        if (t) return t;
        await new Promise(r => setTimeout(r, 100));
    }
    return null;
  } catch {
    return null;
  }
}

export async function getMutationHeaders(init?: HeadersInit): Promise<Headers> {
  const headers = new Headers(init);
  const csrfToken = await ensureCsrfToken();
  if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  return headers;
}

export function setAuthToken(token: string, expiresInSec?: number): void {
  if (typeof window !== "undefined") {
    sessionStorage.setItem(_TOKEN_KEY, token);
    if (expiresInSec) {
      sessionStorage.setItem(_TOKEN_EXPIRY_KEY, String(Date.now() + expiresInSec * 1000));
    }
  }
}

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  const expiry = sessionStorage.getItem(_TOKEN_EXPIRY_KEY);
  if (expiry && Date.now() > Number(expiry)) {
    sessionStorage.removeItem(_TOKEN_KEY);
    sessionStorage.removeItem(_TOKEN_EXPIRY_KEY);
    return null;
  }
  return sessionStorage.getItem(_TOKEN_KEY);
}

export function clearAuthToken(): void {
  if (typeof window !== "undefined") {
    sessionStorage.removeItem(_TOKEN_KEY);
    sessionStorage.removeItem(_TOKEN_EXPIRY_KEY);
  }
}

export function isAuthenticated(): boolean {
  if (getAuthToken() !== null) return true;
  if (typeof document !== "undefined") {
    return document.cookie.includes("fc_session=") || document.cookie.includes("sessionid=");
  }
  return false;
}
