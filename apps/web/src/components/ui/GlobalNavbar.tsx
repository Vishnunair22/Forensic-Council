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

    const shouldReset = hasActiveSession || pathname !== "/";

    playSound(shouldReset ? "reset" : "hum");

    if (shouldReset) {
      resetActiveInvestigation(queryClient);
      router.push("/", { scroll: true });
      return;
    }

    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [pathname, router, playSound, hasActiveSession, queryClient]);

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
      className={`fixed top-0 inset-x-0 w-full z-[10001] transition-[transform,opacity] duration-300 ease-in-out border-b border-white/10 bg-[#02040A]/80 backdrop-blur-md ${
        isVisible || isKeyboardUser ? "translate-y-0 opacity-100" : "-translate-y-full opacity-0 pointer-events-none"
      }`}
    >
      <div
        className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center"
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        <button
          type="button"
          onClick={handleLogoClick}
          aria-label={hasActiveSession || pathname !== "/" ? "Reset and return to Forensic Council home" : "Return to top"}
          aria-current={pathname === "/" ? "page" : undefined}
          className="flex items-center rounded-sm fc-transition fc-focus-ring outline-none"
        >
          <BrandLogo size="sm" isHovered={isHovered} />
        </button>

      </div>
    </nav>
  );
}
