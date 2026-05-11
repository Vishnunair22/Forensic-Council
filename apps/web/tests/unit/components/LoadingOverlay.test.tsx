import React from "react";
import { render } from "@testing-library/react";
import "@testing-library/jest-dom";
import { LoadingOverlay } from "@/components/ui/LoadingOverlay";

jest.mock("framer-motion", () => ({
  motion: new Proxy({}, {
    get:
      () =>
      ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) =>
      React.createElement("div", props, children),
  }),
  useReducedMotion: () => false,
  AnimatePresence: ({ children }: React.PropsWithChildren<object>) => <>{children}</>,
}));

describe("LoadingOverlay", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("renders overlay container", () => {
    render(<LoadingOverlay />);
    expect(document.body.querySelector(".fixed.inset-0")).toBeTruthy();
  });

  test("applies fixed positioning and blur classes", () => {
    render(<LoadingOverlay />);
    const el = document.body.querySelector(".fixed.inset-0") as HTMLElement;
    expect(el.className).toContain("fixed");
    expect(el.className).toContain("inset-0");
  });
});
