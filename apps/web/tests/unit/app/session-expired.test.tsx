import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import SessionExpiredPage from "@/app/session-expired/page";

const mockPush = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock("@tanstack/react-query", () => ({
  useQueryClient: jest.fn(() => ({
    clear: jest.fn(),
  })),
}));

describe("SessionExpiredPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // T-C-1: SessionExpiredClient branches on window.location.pathname.
    // jsdom defaults to "/" — the production "Return to Hub" button only
    // dispatches `fc:reset-home` (no router.push). For the test to
    // observe router.push("/"), the pathname must be something other
    // than "/" (the real session-expired route).
    window.history.replaceState({}, "", "/session-expired");
  });

  it("renders the expired-session guidance", () => {
    render(<SessionExpiredPage />);

    expect(screen.getByRole("heading", { name: /session expired/i })).toBeInTheDocument();
    expect(screen.getByText(/authenticate again to continue forensic analysis/i)).toBeInTheDocument();
  });

  it("routes back to the dashboard", () => {
    render(<SessionExpiredPage />);

    fireEvent.click(screen.getByRole("button", { name: /return to hub/i }));

    expect(mockPush).toHaveBeenCalledWith("/");
  });
});
