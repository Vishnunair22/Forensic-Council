"use client";

import { useCallback, useState, useEffect, useRef } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { useSound } from "@/hooks/useSound";
import { BrandLogo } from "./BrandLogo";
import { storage, sessionOnlyStorage } from "@/lib/storage";
import { __pendingFileStore } from "@/lib/pendingFileStore";
import { arbiterControl } from "@/lib/arbiterControl";

export function GlobalNavbar() {
  const router = useRouter();
  const pathname = usePathname();
  const { playSound } = useSound();
  const queryClient = useQueryClient();
  const [isHovered, setIsHovered] = useState(false);
  const [hasActiveSession, setHasActiveSession] = useState(false);
  const [isVisible, setIsVisible] = useState(true);
  const lastScrollY = useRef(0);

  // Poll for active session to show destructive reset badge
  useEffect(() => {
    if (typeof window === "undefined") return;
    
    const checkSession = () => {
      setHasActiveSession(!!storage.getItem("forensic_session_id"));
    };

    checkSession();
    const interval = setInterval(checkSession, 1500);
    window.addEventListener("fc_storage_update", checkSession);
    
    return () => {
      clearInterval(interval);
      window.removeEventListener("fc_storage_update", checkSession);
    };
  }, []);

  // Hide navbar on scroll down, show on scroll up
  useEffect(() => {
    if (typeof window === "undefined") return;

    const handleScroll = () => {
      const currentScrollY = window.scrollY;
      if (currentScrollY < 60) {
        // Always show near top of page
        setIsVisible(true);
      } else if (currentScrollY > lastScrollY.current) {
        // Scrolling down — hide
        setIsVisible(false);
      } else {
        // Scrolling up — show
        setIsVisible(true);
      }
      lastScrollY.current = currentScrollY;
    };

    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const handleLogoClick = useCallback(() => {
    if (typeof window === "undefined") return;
    playSound(hasActiveSession && pathname !== "/" ? "reset" : "hum");

    // Always perform full reset — navbar is universal reset button
    arbiterControl.abort();
    queryClient.clear();
    storage.clearAllForensicKeys();
    sessionOnlyStorage.clearAllForensicKeys();

    // Expire the session cookie so the server-side /result redirect
    // doesn't point back to the old session after a reset.
    document.cookie = "forensic_session_id=; path=/; max-age=0; SameSite=Lax";

    // Clean up the CSS bridge attribute that handleAcceptAnalysis stamps
    // on body before navigating to /result — prevents it from getting stuck
    // if the user resets mid-transition.
    document.body.removeAttribute("data-fc-loading");

    // Also clear agent-keyed localStorage entries
    Object.keys(localStorage).forEach(key => {
      if (key.startsWith("forensic_initial_agents:") || key.startsWith("forensic_deep_agents:")) {
        localStorage.removeItem(key);
      }
    });

    __pendingFileStore.file = null;
    __pendingFileStore.authPromise = null;

    // Prevent auto-reconnect on any subsequent /evidence visit
    sessionOnlyStorage.setItem("fc_no_reconnect", "1");

    window.dispatchEvent(new Event("fc:reset-home"));

    if (pathname === "/") {
      window.scrollTo({ top: 0, behavior: "smooth" });
    } else {
      router.push("/", { scroll: true });
    }
  }, [pathname, router, playSound, hasActiveSession, queryClient]);

  return (
    <nav
      aria-label="Main navigation"
      {...(!isVisible ? { inert: true } : {})}
      className={`fixed top-4 left-4 sm:top-6 sm:left-6 z-[10001] transition-[transform,opacity] duration-300 ease-in-out ${
        isVisible ? "translate-y-0 opacity-100" : "-translate-y-24 opacity-0 pointer-events-none"
      }`}
    >
      <button
        type="button"
        className="group flex items-center px-3.5 py-2 sm:px-4 sm:py-2.5 rounded-full border transition-all duration-200 relative"
        style={{
          background: "rgba(6,10,20,0.92)",
          borderColor: "rgba(165,200,255,0.10)",
          backdropFilter: "blur(16px)",
          WebkitBackdropFilter: "blur(16px)",
          boxShadow: "0 8px 32px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.05)",
        }}
        onClick={handleLogoClick}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        aria-label="Return to Forensic Council home"
        aria-current={pathname === "/" ? "page" : undefined}
      >
        <BrandLogo size="sm" isHovered={isHovered} />

        {/* Fix D: Destructive Reset indicator (pulsing red dot) */}
        {hasActiveSession && pathname !== "/" && (
          <div className="absolute -top-1 -right-1 flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500"></span>
          </div>
        )}
      </button>

    </nav>
  );
}
