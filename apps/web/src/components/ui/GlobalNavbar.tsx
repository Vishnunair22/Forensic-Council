"use client";

import { useCallback, useState, useEffect, useRef } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { useReducedMotion } from "framer-motion";
import { useSound } from "@/hooks/useSound";
import { BrandLogo } from "./BrandLogo";
import { resetActiveInvestigation } from "@/lib/appReset";
import { storage } from "@/lib/storage";

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

  // React to active session state changes via storage events, focus, and visibility
  useEffect(() => {
    if (typeof window === "undefined") return;
    
    const checkSession = () => {
      setHasActiveSession(!!storage.getItem("forensic_session_id"));
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

  // Hide navbar on scroll down, show on scroll up
  // Skip auto-hide for users who prefer reduced motion — they need predictable focus behavior
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (prefersReducedMotion) {
      setIsVisible(true);
      return;
    }

    const handleScroll = () => {
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

  // Detect keyboard navigation and force navbar visible while user tabs through
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

    playSound(hasActiveSession && pathname !== "/" ? "reset" : "hum");

    if (pathname === "/") {
      window.scrollTo({ top: 0, behavior: "smooth" });
    } else {
      router.push("/", { scroll: true });
    }
  }, [pathname, router, playSound, hasActiveSession]);

  const handleResetClick = useCallback(() => {
    if (typeof window === "undefined") return;
    playSound("reset");
    resetActiveInvestigation(queryClient);
    router.push("/", { scroll: true });
  }, [queryClient, router, playSound]);

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
      className={`fixed top-4 left-4 sm:top-6 sm:left-6 z-[10001] transition-[transform,opacity] duration-300 ease-in-out ${
        isVisible || isKeyboardUser ? "translate-y-0 opacity-100" : "-translate-y-24 opacity-0 pointer-events-none"
      }`}
    >
      <div
        className="group flex items-center px-3.5 py-2 sm:px-4 sm:py-2.5 rounded-full border transition-all duration-200 relative"
        style={{
          background: "rgba(6,10,20,0.92)",
          borderColor: "rgba(165,200,255,0.10)",
          backdropFilter: "blur(16px)",
          WebkitBackdropFilter: "blur(16px)",
          boxShadow: "0 8px 32px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.05)",
        }}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        <button
          type="button"
          onClick={handleLogoClick}
          aria-label="Return to Forensic Council home"
          aria-current={pathname === "/" ? "page" : undefined}
          className="flex items-center rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/70"
        >
          <BrandLogo size="sm" isHovered={isHovered} />
        </button>

        {(hasActiveSession || pathname !== "/") && (
          <button
            type="button"
            onClick={handleResetClick}
            className="ml-2 px-3 py-1.5 text-[10px] font-mono font-bold uppercase tracking-[0.15em] rounded-full border transition-all duration-200"
            style={{
              color: "rgba(255,255,255,0.55)",
              background: "rgba(239,68,68,0.12)",
              borderColor: "rgba(239,68,68,0.25)",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = "rgba(255,255,255,0.9)";
              e.currentTarget.style.background = "rgba(239,68,68,0.22)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = "rgba(255,255,255,0.55)";
              e.currentTarget.style.background = "rgba(239,68,68,0.12)";
            }}
            aria-label="Reset active investigation"
          >
            Reset
          </button>
        )}
      </div>
    </nav>
  );
}
