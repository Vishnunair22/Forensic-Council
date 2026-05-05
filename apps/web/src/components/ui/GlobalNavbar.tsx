"use client";

import { useCallback, useState, useEffect } from "react";
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

  const handleLogoClick = useCallback(() => {
    if (typeof window === "undefined") return;

    playSound("hum");

    // Fix A: Navbar owns the reset logic if navigating away from analysis
    if (pathname !== "/") {
      arbiterControl.abort();
      storage.clearAllForensicKeys();
      sessionOnlyStorage.clearAllForensicKeys();
      __pendingFileStore.file = null;
      __pendingFileStore.authPromise = null;
    }

    window.dispatchEvent(new Event("fc:reset-home"));

    if (pathname === "/") {
      window.scrollTo({ top: 0, behavior: "smooth" });
    } else {
      router.push("/", { scroll: true });
    }
  }, [pathname, router, playSound]);

  return (
    <nav
      aria-label="Main navigation"
      className="fixed top-8 left-8 z-[500]"
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
