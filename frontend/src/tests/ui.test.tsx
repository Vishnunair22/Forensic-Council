import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import Home from "../app/page";
import { useRouter } from "next/navigation";

// Mock next/navigation
jest.mock("next/navigation", () => ({
  useRouter: jest.fn(),
}));

jest.mock("@/components/evidence/UploadModal", () => ({
  UploadModal: ({ onFileSelected }: { onFileSelected: (file: File) => void }) => (
    <button
      type="button"
      onClick={() =>
        onFileSelected(new File(["x"], "evidence.jpg", { type: "image/jpeg" }))
      }
    >
      Analyse Evidence
    </button>
  ),
}));

jest.mock("@/components/evidence/UploadSuccessModal", () => ({
  UploadSuccessModal: () => <div>Upload ready</div>,
}));

jest.mock("@/components/result/ExampleReportSection", () => ({
  ExampleReportSection: () => <div>Example report</div>,
}));

jest.mock("lucide-react", () => {
  return new Proxy(
    {},
    {
      get: () =>
        ({ ...props }: React.ComponentPropsWithoutRef<"svg">) =>
          React.createElement("svg", props),
    },
  );
});

describe("Home Page UI Tests", () => {
  const mockPush = jest.fn();

  beforeEach(() => {
    (useRouter as jest.Mock).mockReturnValue({
      push: mockPush,
    });
  });

  test("renders hero title with gradient text", () => {
    render(<Home />);
    const heading = screen.getByText(/Forensic Intelligence/i);
    expect(heading).toBeInTheDocument();
  });

  test("renders 'Launch System' button and it opens upload modal", () => {
    render(<Home />);
    const launchButton = screen.getByText(/Launch System/i);
    expect(launchButton).toBeInTheDocument();
    
    fireEvent.click(launchButton);
    // After clicking, the UploadModal should be rendered if we didn't mock it too deeply
    // But since it's a 'use client' component with state, it should show up.
    expect(screen.getByText(/Analyse Evidence/i)).toBeInTheDocument();
  });

  test("contains forensic agent descriptions", () => {
    render(<Home />);
    expect(screen.getByText(/The Council of Agents/i)).toBeInTheDocument();
    expect(screen.getByText(/Five independent AI specialists/i)).toBeInTheDocument();
  });

  test("contains FAQ section", () => {
    render(<Home />);
    expect(screen.getByText(/Frequently Asked Questions/i)).toBeInTheDocument();
    expect(screen.getByText(/Is the analysis permanent\?/i)).toBeInTheDocument();
  });
});
