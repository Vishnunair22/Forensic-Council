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

const RAW_API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";
const INTERNAL_API_BASE = process.env.INTERNAL_API_URL ?? "";

export const API_BASE: string =
  typeof window !== "undefined"
    ? RAW_API_BASE && RAW_API_BASE !== "/"
      ? RAW_API_BASE.replace(/\/$/, "")
      : window.location.origin
    : INTERNAL_API_BASE || RAW_API_BASE || "http://backend:8000";

export const WS_BASE: string = (() => {
  if (typeof window === "undefined") return API_BASE.replace(/^http/, "ws");
  
  // If we are accessing the UI via port 3000 (Next.js dev server directly),
  // we must redirect WebSocket traffic to port 80 (Caddy) because Next.js 
  // doesn't proxy WebSockets.
  if (window.location.port === "3000") {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.hostname}`; // Defaults to port 80/443
  }

  return API_BASE.replace(/^https:\/\//, "wss://").replace(/^http:\/\//, "ws://");
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
    return document.cookie.includes("access_token=");
  }
  return false;
}
