import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { UploadSuccessModal } from "@/components/evidence/UploadSuccessModal";

jest.mock("@/hooks/useSound", () => ({ useSound: () => ({ playSound: jest.fn() }) }));
jest.mock("framer-motion", () => ({
  motion: {
    div: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) =>
      React.createElement("div", props, children),
    span: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) =>
      React.createElement("span", props, children),
  },
  useReducedMotion: () => false,
}));

URL.createObjectURL = jest.fn(() => "blob:mock");
URL.revokeObjectURL = jest.fn();

const testFile = new File(["test-content"], "evidence.jpg", { type: "image/jpeg" });

describe("BUG-09 — Filename and hash rendered below preview (stacked card)", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders file name below the preview area, not beside it", () => {
    const { container } = render(
      <UploadSuccessModal file={testFile} onStartAnalysis={jest.fn()} onDismiss={jest.fn()} />,
    );

    const previewDivs = container.querySelectorAll(".border-b.border-white\\/5");
    expect(previewDivs.length).toBeGreaterThanOrEqual(1);

    expect(screen.getByText("evidence.jpg")).toBeInTheDocument();
    expect(screen.getByText("SHA-256 Checksum")).toBeInTheDocument();
  });

  it("does not use grid-cols layout for metadata", () => {
    const { container } = render(
      <UploadSuccessModal file={testFile} onStartAnalysis={jest.fn()} onDismiss={jest.fn()} />,
    );

    expect(container.querySelector('[class*="grid-cols-1"]')).not.toBeInTheDocument();
    expect(container.querySelector('[class*="md:col-span-2"]')).not.toBeInTheDocument();
    expect(container.querySelector('[class*="md:col-span-3"]')).not.toBeInTheDocument();
  });

  it("shows file size in the metadata footer", () => {
    render(
      <UploadSuccessModal file={testFile} onStartAnalysis={jest.fn()} onDismiss={jest.fn()} />,
    );

    expect(screen.getByText(/12\s*bytes|12\s*B/i)).toBeInTheDocument();
  });
});
