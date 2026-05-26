import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";

const mockPush = jest.fn();
const mockRefresh = jest.fn();
let mockPathname = "/evidence";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, refresh: mockRefresh }),
  usePathname: () => mockPathname,
}));
jest.mock("@/hooks/useSound", () => ({ useSound: () => ({ playSound: jest.fn() }) }));
jest.mock("framer-motion", () => ({ useReducedMotion: () => false }));
jest.mock("@tanstack/react-query", () => ({ useQueryClient: () => ({ clear: jest.fn() }) }));
jest.mock("@/lib/appReset", () => ({ resetActiveInvestigation: jest.fn() }));
jest.mock("@/lib/storage", () => ({
  storage: { getItem: jest.fn(() => null), setItem: jest.fn(), removeItem: jest.fn() },
  sessionOnlyStorage: { getItem: jest.fn(() => null), setItem: jest.fn(), removeItem: jest.fn() },
}));
jest.mock("@/lib/storageKeys", () => ({ STORAGE_KEYS: { SESSION_ID: "forensic_session_id" } }));
jest.mock("@/components/ui/BrandLogo", () => ({ BrandLogo: () => <span>Logo</span> }));

describe("BUG-02 — Navbar logo uses router.push (SPA nav) not window.location.href", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockPathname = "/evidence";
  });

  it("calls router.push('/') instead of setting window.location.href when on /evidence", () => {
    const { GlobalNavbar } = require("@/components/ui/GlobalNavbar");
    render(<GlobalNavbar />);
    const logoBtn = screen.getByRole("button", { name: /reset and return/i });
    fireEvent.click(logoBtn);
    expect(mockPush).toHaveBeenCalledWith("/");
  });
});
