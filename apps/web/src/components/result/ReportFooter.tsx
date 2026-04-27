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
        className="btn-horizon-outline px-10 py-4"
        aria-label="Return to the home page"
      >
        <Home className="w-4 h-4 mr-2" aria-hidden="true" />
        BACK TO HUB
      </button>

    </footer>
  );
}
