"use client";

import { useCallback, useState, useEffect, useRef } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useSound } from "@/hooks/useSound";
import { BrandLogo } from "./BrandLogo";
import { storage, sessionOnlyStorage } from "@/lib/storage";
import { __pendingFileStore } from "@/lib/pendingFileStore";
import { arbiterControl } from "@/lib/arbiterControl";

export function GlobalNavbar() {
  const router = useRouter();
  const pathname = usePathname();
  const { playSound } = useSound();
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
    storage.clearAllForensicKeys();
    sessionOnlyStorage.clearAllForensicKeys();
    
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
  }, [pathname, router, playSound, hasActiveSession]);

  return (
    <nav
      aria-label="Main navigation"
      className={`fixed top-6 left-6 z-[10001] transition-transform duration-300 ease-in-out ${
        isVisible ? "translate-y-0 opacity-100" : "-translate-y-24 opacity-0 pointer-events-none"
      }`}
    >
      <button
        type="button"
        className="group flex items-center px-5 py-3 bg-surface-2 rounded-full border border-white/10 shadow-2xl hover:bg-surface-3 transition-all active:scale-95 relative"
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
