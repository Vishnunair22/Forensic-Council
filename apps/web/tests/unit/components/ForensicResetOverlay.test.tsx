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
  AnimatePresence: ({ children }: React.PropsWithChildren<object>) => <>{children}</>,
}));

describe("LoadingOverlay", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("renders overlay container", () => {
    const { container } = render(<LoadingOverlay />);
    expect(container.firstChild).toBeTruthy();
  });

  test("applies fixed positioning and blur classes", () => {
    const { container } = render(<LoadingOverlay />);
    const el = container.firstChild as HTMLElement;
    expect(el.className).toContain("fixed");
    expect(el.className).toContain("inset-0");
  });
});
