"use client";

import { Home } from "lucide-react";

interface ReportFooterProps {
  handleHome: () => void;
}

export function ReportFooter({ handleHome }: ReportFooterProps) {
  return (
    <footer
      className="pt-8 pb-32 flex flex-col sm:flex-row items-center justify-center gap-3"
      aria-label="Post-analysis actions"
    >
      <button
        type="button"
        onClick={handleHome}
        className="btn-pill-secondary text-xs flex items-center gap-2"
        aria-label="Return to the home page"
      >
        <Home className="w-4 h-4" aria-hidden="true" />
        Back to Home
      </button>
    </footer>
  );
}
