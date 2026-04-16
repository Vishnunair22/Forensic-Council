import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import ForensicResetOverlay from "@/components/ui/ForensicResetOverlay";

describe("ForensicResetOverlay", () => {
  const mockOnReset = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("renders with loading message", () => {
    render(<ForensicResetOverlay onReset={mockOnReset} isResetting={true} />);
    expect(screen.getByText(/Resetting workspace/i)).toBeInTheDocument();
  });

  test("renders with finished message and action button when not resetting", () => {
    render(<ForensicResetOverlay onReset={mockOnReset} isResetting={false} />);
    expect(screen.getByText(/Workspace Reset/i)).toBeInTheDocument();
    
    const btn = screen.getByRole("button", { name: /continue/i });
    expect(btn).toBeInTheDocument();
    
    fireEvent.click(btn);
    expect(mockOnReset).toHaveBeenCalled();
  });
});
