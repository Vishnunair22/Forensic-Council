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

const mockPlaySound = jest.fn();
jest.mock("@/hooks/useSound", () => ({ useSound: () => ({ playSound: mockPlaySound }) }));
jest.mock("framer-motion", () => ({ useReducedMotion: () => false }));
jest.mock("@tanstack/react-query", () => ({ useQueryClient: () => ({ clear: jest.fn() }) }));
jest.mock("@/lib/appReset", () => ({
  resetActiveInvestigation: jest.fn(),
  hasResettableInvestigationState: jest.fn(() => false),
}));
jest.mock("@/lib/storage", () => ({
  storage: { getItem: jest.fn(() => null), setItem: jest.fn(), removeItem: jest.fn() },
  sessionOnlyStorage: { getItem: jest.fn(() => null), setItem: jest.fn(), removeItem: jest.fn() },
}));
jest.mock("@/lib/storageKeys", () => ({ STORAGE_KEYS: { SESSION_ID: "forensic_session_id" } }));
jest.mock("@/components/ui/BrandLogo", () => ({ BrandLogo: () => <span>Logo</span> }));

describe("GlobalNavbar — logo click behaviour", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("no active session on /evidence", () => {
    beforeEach(() => {
      mockPathname = "/evidence";
    });

    it("calls router.push('/') for SPA navigation (not window.location)", () => {
      const { GlobalNavbar } = require("@/components/ui/GlobalNavbar");
      render(<GlobalNavbar />);
      const logoBtn = screen.getByRole("button", { name: /forensic council/i });
      fireEvent.click(logoBtn);
      expect(mockPush).toHaveBeenCalledWith("/");
    });

    it("plays 'hum' — not the abort 'reset' sound — when no session exists", () => {
      const { GlobalNavbar } = require("@/components/ui/GlobalNavbar");
      render(<GlobalNavbar />);
      const logoBtn = screen.getByRole("button", { name: /forensic council/i });
      fireEvent.click(logoBtn);
      expect(mockPlaySound).toHaveBeenCalledWith("hum");
      expect(mockPlaySound).not.toHaveBeenCalledWith("reset");
    });
  });

  describe("no active session on / (home)", () => {
    beforeEach(() => {
      mockPathname = "/";
    });

    it("does not call router.push when already on home", () => {
      const { GlobalNavbar } = require("@/components/ui/GlobalNavbar");
      render(<GlobalNavbar />);
      const logoBtn = screen.getByRole("button", { name: /scroll to top/i });
      fireEvent.click(logoBtn);
      expect(mockPush).not.toHaveBeenCalled();
    });

    it("plays 'hum' on home with no session", () => {
      const { GlobalNavbar } = require("@/components/ui/GlobalNavbar");
      render(<GlobalNavbar />);
      const logoBtn = screen.getByRole("button", { name: /scroll to top/i });
      fireEvent.click(logoBtn);
      expect(mockPlaySound).toHaveBeenCalledWith("hum");
    });
  });

  describe("active session", () => {
    beforeEach(() => {
      mockPathname = "/evidence";
      const { hasResettableInvestigationState } = require("@/lib/appReset");
      (hasResettableInvestigationState as jest.Mock).mockReturnValue(true);
    });

    it("opens confirm dialog instead of navigating when session is active", () => {
      const { GlobalNavbar } = require("@/components/ui/GlobalNavbar");
      render(<GlobalNavbar />);
      const logoBtn = screen.getByRole("button", { name: /reset and return/i });
      fireEvent.click(logoBtn);
      // Dialog should open — router.push must NOT be called directly
      expect(mockPush).not.toHaveBeenCalled();
    });

    it("does not play any sound on first logo click when session is active (dialog opens first)", () => {
      const { GlobalNavbar } = require("@/components/ui/GlobalNavbar");
      render(<GlobalNavbar />);
      const logoBtn = screen.getByRole("button", { name: /reset and return/i });
      fireEvent.click(logoBtn);
      expect(mockPlaySound).not.toHaveBeenCalled();
    });
  });
});
