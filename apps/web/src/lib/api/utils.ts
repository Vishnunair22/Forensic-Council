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
const INTERNAL_API_URL = process.env.INTERNAL_API_URL ?? "";

export const API_BASE: string =
  typeof window !== "undefined"
    ? RAW_API_BASE && RAW_API_BASE !== "/"
      ? RAW_API_BASE.replace(/\/$/, "")
      : window.location.origin
    : INTERNAL_API_URL || RAW_API_BASE || "http://backend:8000";

export function getWSBase(): string {
  if (typeof window === "undefined") return "ws://backend:8000";

  if (RAW_API_BASE) {
    try {
      const url = new URL(RAW_API_BASE);
      const wsProto = url.protocol === "https:" ? "wss:" : "ws:";
      return `${wsProto}//${url.host}`;
    } catch { /* fall through */ }
  }

  // Dev convenience — Next.js on :3000, backend on :8000
  if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
    return `ws://${window.location.hostname}:8000`;
  }

  // Production fallback: same host (valid only if a WS-capable reverse proxy handles upgrades)
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  console.warn(
    "[FC] NEXT_PUBLIC_API_URL not set — WebSocket will connect to",
    `${protocol}//${window.location.host}. Ensure your reverse proxy forwards WS upgrades to the backend.`
  );
  return `${protocol}//${window.location.host}`;
}



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
