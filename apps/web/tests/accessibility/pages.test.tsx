/**
 * Accessibility Tests — Pages & Landmarks
 * ========================================
 * Validates WCAG 2.1 AA landmarks and semantic structure for:
 * - Start Page (Landing)
 * - Result Page (Report)
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import Home from "@/app/page";

// Mocks for Next.js and API
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock("@/components/evidence/UploadModal", () => ({
  UploadModal: () => <div>Upload modal</div>,
}));

jest.mock("@/components/evidence/UploadSuccessModal", () => ({
  UploadSuccessModal: () => <div>Upload ready</div>,
}));

jest.mock("lucide-react", () => {
  const React = require("react");
  return new Proxy(
    {},
    {
      get: () =>
        ({ ...props }: React.ComponentPropsWithoutRef<"svg">) =>
          React.createElement("svg", props),
    },
  );
});

describe("Start Page (Home) Structure", () => {
  it("contains a single H1 landmark", () => {
    render(<Home />);
    const headings = screen.getAllByRole("heading", { level: 1 });
    expect(headings.length).toBe(1);
  });
});
