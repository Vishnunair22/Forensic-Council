"use client";

import { useState, useCallback } from "react";
import { useRouter, usePathname } from "next/navigation";
import { AnimatePresence } from "framer-motion";
import { useSound } from "@/hooks/useSound";
import { ForensicResetOverlay } from "./ForensicResetOverlay";
import { BrandLogo } from "./BrandLogo";

export function GlobalNavbar() {
  const router = useRouter();
  const pathname = usePathname();
  const [isResetting, setIsResetting] = useState(false);
  const { playSound } = useSound();

  const handleLogoClick = useCallback(() => {
    if (typeof window === "undefined") return;

    playSound("hum");
    setIsResetting(true);

    window.dispatchEvent(new Event("fc:reset-home"));

    setTimeout(() => {
        if (pathname === "/") {
          window.scrollTo({ top: 0, behavior: "smooth" });
          setTimeout(() => {
            window.dispatchEvent(new Event("fc:reset-home"));
            setIsResetting(false);
          }, 200);
        } else {
          router.push("/", { scroll: true });
          setTimeout(() => {
            window.dispatchEvent(new Event("fc:reset-home"));
            setIsResetting(false);
          }, 200);
        }
    }, 400); 
  }, [pathname, router, playSound]);

  return (
    <nav
      aria-label="Main navigation"
      className="fixed top-8 left-8 z-[500]"
    >
      <AnimatePresence>
        {isResetting && <ForensicResetOverlay />}
      </AnimatePresence>

      <button
        type="button"
        className="flex items-center px-6 py-4 border border-white bg-black text-white cursor-pointer"
        onClick={handleLogoClick}
        aria-label="Return to Forensic Council home"
        aria-current={pathname === "/" ? "page" : undefined}
      >
        <BrandLogo size="sm" isHovered={false} />
      </button>
    </nav>
  );
}
