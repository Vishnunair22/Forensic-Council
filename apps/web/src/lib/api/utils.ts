/**
 * Forensic Council — API Utilities
 */

import { STORAGE_KEYS } from "@/lib/storageKeys";

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

  // When the app is reached through the Next.js dev server on :3000,
  // route WebSocket through Caddy on :80 so the WS upgrade goes through
  // the same reverse proxy as all other API traffic. Port 8000 is not
  // directly exposed in the default docker-compose stack (only via the
  // docker-compose.dev.yml overlay), so connecting to :8000 from the
  // browser would silently fail and fall back to SSE every time.
  if (
    (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") &&
    window.location.port === "3000"
  ) {
    return `ws://${window.location.hostname}`;
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
    await fetch(`${API_BASE}/api/v1/auth/me`, {
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
    sessionStorage.setItem(STORAGE_KEYS.AUTH_TOKEN, token);
    if (expiresInSec) {
      sessionStorage.setItem(STORAGE_KEYS.AUTH_TOKEN_EXPIRY, String(Date.now() + expiresInSec * 1000));
    }
  }
}

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  const expiry = sessionStorage.getItem(STORAGE_KEYS.AUTH_TOKEN_EXPIRY);
  if (expiry) {
    const expiryTime = Number(expiry);
    const GRACE_MS = 30_000; // 30-second grace period for in-flight requests
    if (Date.now() > expiryTime + GRACE_MS) {
      // Expired for more than 30s — hard clear
      sessionStorage.removeItem(STORAGE_KEYS.AUTH_TOKEN);
      sessionStorage.removeItem(STORAGE_KEYS.AUTH_TOKEN_EXPIRY);
      return null;
    }
    if (Date.now() > expiryTime) {
      // Expired within grace window — return the token so in-flight requests
      // are not abruptly terminated. The token will be cleared on next
      // non-grace expiry check.
      return sessionStorage.getItem(STORAGE_KEYS.AUTH_TOKEN);
    }
  }
  return sessionStorage.getItem(STORAGE_KEYS.AUTH_TOKEN);
}

export function clearAuthToken(): void {
  if (typeof window !== "undefined") {
    sessionStorage.removeItem(STORAGE_KEYS.AUTH_TOKEN);
    sessionStorage.removeItem(STORAGE_KEYS.AUTH_TOKEN_EXPIRY);
  }
}

export function isAuthenticated(): boolean {
  if (getAuthToken() !== null) return true;
  if (typeof document !== "undefined") {
    // access_token is set HttpOnly by /api/auth/demo and the backend, so it is
    // normally invisible to document.cookie — keep the check for non-HttpOnly
    // token setups, but also check csrf_token, which is deliberately
    // JS-readable and is issued/expired in lockstep with the access token.
    return (
      document.cookie.includes("access_token=") ||
      document.cookie.includes("csrf_token=")
    );
  }
  return false;
}

// ── Dev-only startup diagnostics ─────────────────────────────────────────────
// Helps diagnose frontend/backend target mismatches in local development.

export function logApiTargetDiagnostics(): void {
  if (!isDev || typeof window === "undefined") return;
  dbg.log("[FC startup] API_BASE", API_BASE);
  dbg.log("[FC startup] WS_BASE", getWSBase());
  dbg.log("[FC startup] location", window.location.origin);
}
