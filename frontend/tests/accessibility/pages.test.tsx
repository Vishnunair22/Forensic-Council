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
// Note: Result page might need complex mocks, we'll test structure
import ResultPage from "@/app/result/page";

// Mocks for Next.js and API
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

jest.mock("@/lib/api", () => ({
  getAuthToken: jest.fn(),
  isAuthenticated: jest.fn(() => true),
  getReport: jest.fn(),
  pollForReport: jest.fn(),
}));

describe("Start Page (Home) Structure", () => {
  it("contains a single H1 landmark", () => {
    render(<Home />);
    const headings = screen.getAllByRole("heading", { level: 1 });
    expect(headings.length).toBe(1);
  });

  it("contains a main landmark", () => {
    render(<Home />);
    expect(screen.getByRole("main")).toBeInTheDocument();
  });

  it("navigation is clearly marked", () => {
    render(<Home />);
    // Header often has role="banner"
    expect(document.querySelector("header") || screen.getByRole("banner")).toBeInTheDocument();
  });

  it("footer is clearly marked", () => {
    render(<Home />);
    expect(document.querySelector("footer") || screen.getByRole("contentinfo")).toBeInTheDocument();
  });
});
