"use client";

import { usePathname } from "next/navigation";
import { BrandLogo } from "./BrandLogo";

export function GlobalFooter() {
  const pathname = usePathname();

  // Hide on result pages where the report itself serves as the authoritative document
  if (pathname.startsWith("/result")) return null;

  return (
    <footer className="w-full mt-auto relative z-10" role="contentinfo" aria-label="Site footer">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="border-t border-border-subtle py-8 flex flex-col items-center justify-center gap-4">
          <BrandLogo size="sm" />
          <p className="text-xs fc-text-muted text-center max-w-[56ch] leading-relaxed">
            Forensic Council is an academic project and can occasionally make mistakes.
          </p>
        </div>
      </div>
    </footer>
  );
}
