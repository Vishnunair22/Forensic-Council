import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import SessionExpiredPage from "@/app/session-expired/page";

const mockPush = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

describe("SessionExpiredPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders the expired-session guidance", () => {
    render(<SessionExpiredPage />);

    expect(screen.getByRole("heading", { name: /session expired/i })).toBeInTheDocument();
    expect(screen.getByText(/authenticate again to continue forensic analysis/i)).toBeInTheDocument();
  });

  it("routes back to the dashboard", () => {
    render(<SessionExpiredPage />);

    fireEvent.click(screen.getByRole("button", { name: /return to dashboard/i }));

    expect(mockPush).toHaveBeenCalledWith("/");
  });
});
