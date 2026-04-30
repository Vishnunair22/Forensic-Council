import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { ForensicResetOverlay } from "@/components/ui/ForensicResetOverlay";

jest.mock("framer-motion", () => ({
  motion: {
    div: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) =>
      React.createElement("div", props, children),
  },
  AnimatePresence: ({ children }: React.PropsWithChildren<object>) => <>{children}</>,
}));

describe("ForensicResetOverlay", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("renders overlay container", () => {
    const { container } = render(<ForensicResetOverlay />);
    expect(container.firstChild).toBeTruthy();
  });

  test("applies fixed positioning and blur classes", () => {
    const { container } = render(<ForensicResetOverlay />);
    const el = container.firstChild as HTMLElement;
    expect(el.className).toContain("fixed");
    expect(el.className).toContain("backdrop-blur");
  });
});
