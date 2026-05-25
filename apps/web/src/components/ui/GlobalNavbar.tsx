"use client";

import { useCallback, useState, useEffect, useRef } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { useReducedMotion } from "framer-motion";
import { useSound } from "@/hooks/useSound";
import { BrandLogo } from "./BrandLogo";
import { resetActiveInvestigation } from "@/lib/appReset";
import { storage } from "@/lib/storage";
import { STORAGE_KEYS } from "@/lib/storageKeys";

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
  const { playSound } = useSound();
  const prefersReducedMotion = useReducedMotion();
  const queryClient = useQueryClient();
  const [isHovered, setIsHovered] = useState(false);
  const [hasActiveSession, setHasActiveSession] = useState(false);
  const [isVisible, setIsVisible] = useState(true);
  const [isKeyboardUser, setIsKeyboardUser] = useState(false);
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

  const handleLogoClick = useCallback(() => {
    if (typeof window === "undefined") return;

    const shouldReset = hasActiveSession || pathname !== "/";
    playSound(shouldReset ? "reset" : "hum");

    if (shouldReset) {
      resetActiveInvestigation(queryClient);
      if (pathname === "/") {
        router.refresh();
        window.scrollTo({ top: 0, behavior: "smooth" });
      } else {
        window.location.href = "/";
      }
      return;
    }

    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [pathname, router, playSound, hasActiveSession, queryClient]);

  const pageLabel = getPageLabel(pathname);

  return (
    <nav
      aria-label="Main navigation"
      onFocusCapture={() => { setIsVisible(true); setIsKeyboardUser(true); }}
      onBlurCapture={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
          setIsKeyboardUser(false);
        }
      }}
      {...(!isVisible && !isKeyboardUser ? { inert: true } : {})}
      className={`fixed top-0 inset-x-0 z-50 h-16 fc-surface-elevated rounded-none transition-[transform,opacity] duration-200 ease-in-out ${
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
  );
}
