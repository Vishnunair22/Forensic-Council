"use client";

import { useCallback, useState, useEffect, useRef } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { useReducedMotion } from "framer-motion";
import { Volume2, VolumeX } from "lucide-react";
import { useSound } from "@/hooks/useSound";
import { BrandLogo } from "./BrandLogo";
import { resetActiveInvestigation } from "@/lib/appReset";
import { storage } from "@/lib/storage";
import { STORAGE_KEYS } from "@/lib/storageKeys";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogClose,
} from "@/components/ui/dialog";

function getPageLabel(pathname: string): string {
  if (pathname === "/") return "Overview";
  if (pathname.startsWith("/evidence")) return "";
  if (pathname.startsWith("/result")) return "Investigation";
  if (pathname.startsWith("/session-expired")) return "Session Expired";
  return "Forensic Council";
}

export function GlobalNavbar() {
  const router = useRouter();
  const pathname = usePathname();
  const { playSound, isMuted, toggleMute } = useSound();
  const prefersReducedMotion = useReducedMotion();
  const queryClient = useQueryClient();
  const [isHovered, setIsHovered] = useState(false);
  const [hasActiveSession, setHasActiveSession] = useState(false);
  const [isVisible, setIsVisible] = useState(true);
  const [isKeyboardUser, setIsKeyboardUser] = useState(false);
  const [confirmResetOpen, setConfirmResetOpen] = useState(false);
  const lastScrollY = useRef(0);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const checkSession = () => {
      setHasActiveSession(!!storage.getItem(STORAGE_KEYS.SESSION_ID));
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") checkSession();
    };

    checkSession();
    window.addEventListener("fc_storage_update", checkSession);
    window.addEventListener("storage", checkSession);
    window.addEventListener("focus", checkSession);
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      window.removeEventListener("fc_storage_update", checkSession);
      window.removeEventListener("storage", checkSession);
      window.removeEventListener("focus", checkSession);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, []);

  const isMounted = useRef(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      isMounted.current = true;
    }, 300);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (prefersReducedMotion) {
      setIsVisible(true);
      return;
    }

    const handleScroll = () => {
      if (!isMounted.current) return;
      const currentScrollY = window.scrollY;
      if (currentScrollY < 60) {
        setIsVisible(true);
      } else if (currentScrollY > lastScrollY.current) {
        setIsVisible(false);
      } else {
        setIsVisible(true);
      }
      lastScrollY.current = currentScrollY;
    };

    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, [prefersReducedMotion]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Tab") setIsKeyboardUser(true);
    };
    const onMouseDown = () => setIsKeyboardUser(false);

    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("mousedown", onMouseDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("mousedown", onMouseDown);
    };
  }, []);

  const executeReset = useCallback(() => {
    resetActiveInvestigation(queryClient);
    if (pathname === "/") {
      router.refresh();
      window.scrollTo({ top: 0, behavior: "smooth" });
    } else {
      router.push("/");
    }
  }, [pathname, router, queryClient]);

  const handleLogoClick = useCallback(() => {
    if (typeof window === "undefined") return;

    if (!hasActiveSession && pathname === "/") {
      playSound("hum");
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }

    // If an active session exists, require confirmation before wiping state.
    if (hasActiveSession) {
      setConfirmResetOpen(true);
      return;
    }

    playSound("reset");
    executeReset();
  }, [pathname, playSound, hasActiveSession, executeReset]);

  const pageLabel = getPageLabel(pathname);

  // Shown only when NEXT_PUBLIC_API_URL is set, meaning API calls go directly
  // to the backend port (bypassing Caddy's security headers and rate limiting).
  const directApiUrl = process.env.NEXT_PUBLIC_API_URL;

  return (
    <>
    <Dialog open={confirmResetOpen} onOpenChange={setConfirmResetOpen}>
      <DialogContent
        className="max-w-sm w-full p-6 space-y-4"
        aria-describedby="reset-confirm-desc"
      >
        <DialogTitle className="text-base font-semibold fc-text-primary">
          Abort investigation?
        </DialogTitle>
        <p id="reset-confirm-desc" className="text-sm fc-text-secondary leading-relaxed">
          The current analysis will be terminated and all local session data cleared. This cannot be undone.
        </p>
        <div className="flex gap-3 pt-1">
          <button
            type="button"
            onClick={() => {
              setConfirmResetOpen(false);
              playSound("reset");
              executeReset();
            }}
            className="flex-1 py-2.5 rounded-full bg-red-500/15 border border-red-500/30 text-red-400 text-sm font-semibold hover:bg-red-500/25 transition-colors"
          >
            Abort &amp; Reset
          </button>
          <DialogClose asChild>
            <button
              type="button"
              className="flex-1 py-2.5 rounded-full fc-surface-elevated border border-border-muted fc-text-secondary text-sm font-semibold hover:border-border-strong transition-colors"
            >
              Keep Going
            </button>
          </DialogClose>
        </div>
      </DialogContent>
    </Dialog>
    {directApiUrl && (
      <div
        role="alert"
        aria-live="polite"
        className="fixed top-0 inset-x-0 z-[60] flex items-center justify-center gap-2 px-4 py-1 text-xs font-mono"
        style={{
          background: "rgba(234,179,8,0.15)",
          borderBottom: "1px solid rgba(234,179,8,0.35)",
          color: "rgba(253,224,71,0.9)",
        }}
      >
        <span aria-hidden="true">⚠</span>
        <span>
          DEV MODE — API calls bypass Caddy (no rate-limit / security headers).{" "}
          <span style={{ opacity: 0.7 }}>NEXT_PUBLIC_API_URL={directApiUrl}</span>
        </span>
      </div>
    )}
    <nav
      aria-label="Main navigation"
      onFocusCapture={() => { setIsVisible(true); setIsKeyboardUser(true); }}
      onBlurCapture={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
          setIsKeyboardUser(false);
        }
      }}
      {...(!isVisible && !isKeyboardUser ? { inert: true } : {})}
      className={`fixed inset-x-0 z-50 h-16 fc-surface-elevated rounded-none transition-[transform,opacity] duration-200 ease-in-out ${directApiUrl ? "top-7" : "top-0"} ${
        isVisible || isKeyboardUser
          ? "translate-y-0 opacity-100"
          : "-translate-y-full opacity-0 pointer-events-none"
      }`}
      style={{
        borderRadius: 0,
        border: "none",
        borderBottom: "1px solid rgba(255,255,255,0.08)",
        boxShadow: "0 1px 0 rgba(147,197,253,0.10), 0 8px 40px rgba(0,0,0,0.45)",
      }}
    >
      {/* Blue bottom accent gradient */}
      <div
        aria-hidden="true"
        className="absolute bottom-0 inset-x-0 h-px pointer-events-none"
        style={{
          background:
            "linear-gradient(90deg, transparent 0%, rgba(147,197,253,0.18) 20%, rgba(59,130,246,0.42) 50%, rgba(147,197,253,0.18) 80%, transparent 100%)",
        }}
      />

      <div
        className="max-w-7xl mx-auto px-4 sm:px-6 h-full flex items-center justify-between gap-4"
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        {/* Brand */}
        <button
          type="button"
          onClick={handleLogoClick}
          aria-label={
            hasActiveSession || pathname !== "/"
              ? "Reset and return to Forensic Council home"
              : "Forensic Council — scroll to top"
          }
          aria-current={pathname === "/" ? "page" : undefined}
          className="flex items-center min-h-[44px] rounded-sm fc-transition fc-focus-ring outline-none shrink-0"
        >
          <BrandLogo size="sm" isHovered={isHovered} />
        </button>

        {/* Right side */}
        <div className="flex items-center gap-3 min-w-0">
          {/* Page label — hidden on smallest screens */}
          {pageLabel && (
            <div
              className="hidden sm:flex items-center gap-2 px-3 py-1 rounded-full shrink-0"
              style={{
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.07)",
              }}
            >
              <span
                className="w-1 h-1 rounded-full shrink-0"
                style={{ background: "rgba(147,197,253,0.55)" }}
                aria-hidden="true"
              />
              <span className="fc-eyebrow fc-text-muted truncate">
                {pageLabel}
              </span>
            </div>
          )}

          {/* Mute toggle */}
          <button
            type="button"
            onClick={toggleMute}
            aria-label={isMuted ? "Unmute sound effects" : "Mute sound effects"}
            aria-pressed={isMuted}
            className="fc-btn-ghost p-0 w-9 h-9 min-h-0 shrink-0"
          >
            {isMuted
              ? <VolumeX size={16} aria-hidden="true" />
              : <Volume2 size={16} aria-hidden="true" />}
          </button>

          {/* Session indicator */}
          {hasActiveSession ? (
            <div className="flex items-center gap-2 shrink-0">
              <span
                className="w-1.5 h-1.5 rounded-full animate-pulse shrink-0"
                style={{
                  background: "rgba(96,165,250,0.90)",
                  boxShadow: "0 0 6px rgba(96,165,250,0.65)",
                }}
              />
            </div>
          ) : (
            <span className="fc-eyebrow fc-text-faint hidden md:inline shrink-0">
              FC — Multi-Agent
            </span>
          )}
        </div>
      </div>
    </nav>
    </>
  );
}
