"use client";

import { useCallback, useState, useEffect, useRef } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { useReducedMotion } from "framer-motion";
import { useSound } from "@/hooks/useSound";
import { BrandLogo } from "./BrandLogo";
import { resetActiveInvestigation, hasResettableInvestigationState } from "@/lib/appReset";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogClose,
} from "@/components/ui/dialog";

export function GlobalNavbar() {
  const router = useRouter();
  const pathname = usePathname();
  const { playSound } = useSound();
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
      setHasActiveSession(hasResettableInvestigationState());
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") checkSession();
    };

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

  useEffect(() => {
    setHasActiveSession(hasResettableInvestigationState());
  }, [pathname]);

  const scrollEnabledRef = useRef(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      scrollEnabledRef.current = true;
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
      if (!scrollEnabledRef.current) return;
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
    void resetActiveInvestigation(queryClient);
    if (pathname === "/") {
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
        role="status"
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
        boxShadow: "0 8px 40px rgba(0,0,0,0.45)",
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
      </div>
    </nav>
    </>
  );
}
