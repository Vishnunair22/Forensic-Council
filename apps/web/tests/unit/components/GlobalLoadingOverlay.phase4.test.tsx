import React from "react";
import { render, screen, act } from "@testing-library/react";
import "@testing-library/jest-dom";
import { GlobalLoadingOverlay } from "@/components/ui/GlobalLoadingOverlay";

let mockPathname = "/evidence";

jest.mock("next/navigation", () => ({
  usePathname: () => mockPathname,
}));
jest.mock("@/lib/storage", () => ({
  storage: { getItem: jest.fn(() => null), setItem: jest.fn(), removeItem: jest.fn() },
  sessionOnlyStorage: {
    getItem: jest.fn((key: string) => {
      if (key === "fc_show_loading") return "true";
      return null;
    }),
    setItem: jest.fn(),
    removeItem: jest.fn(),
  },
}));
jest.mock("@/lib/storageKeys", () => ({
  STORAGE_KEYS: {
    FC_SHOW_LOADING: "fc_show_loading",
    FC_LOADING_TEXT: "fc_loading_text",
    FC_LOADING_DISPATCHED: "fc_loading_dispatched",
    FC_HANDOFF_FIRED: "fc_handoff_fired",
    FC_ARBITER_TRANSITIONING: "fc_arbiter_transitioning",
  },
}));
jest.mock("framer-motion", () => ({
  motion: { div: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => React.createElement("div", props, children) },
  AnimatePresence: ({ children }: React.PropsWithChildren<object>) => React.createElement(React.Fragment, null, children),
  useReducedMotion: () => false,
}));
jest.mock("@/components/ui/LoadingOverlay", () => ({
  LoadingOverlay: () => React.createElement("div", { "data-testid": "loading-overlay" }),
}));

describe("BUG-21 — No ArbiterDeliberationOverlay in GlobalLoadingOverlay", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("renders LoadingOverlay when fc_show_loading is true", () => {
    render(<GlobalLoadingOverlay />);
    expect(screen.getByTestId("loading-overlay")).toBeInTheDocument();
  });

  it("does not render ArbiterDeliberationOverlay (no import used)", () => {
    const { container } = render(<GlobalLoadingOverlay />);
    expect(container.querySelector("[data-testid='arbiter-overlay']")).toBeNull();
  });

  it("overlay dismisses within 5s safety window", () => {
    render(<GlobalLoadingOverlay />);
    expect(screen.getByTestId("loading-overlay")).toBeInTheDocument();

    act(() => {
      jest.advanceTimersByTime(5000);
    });

    expect(screen.queryByTestId("loading-overlay")).not.toBeInTheDocument();
  });

  it("overlay dismisses on fc_storage_update with null value", () => {
    render(<GlobalLoadingOverlay />);
    expect(screen.getByTestId("loading-overlay")).toBeInTheDocument();

    act(() => {
      window.dispatchEvent(
        new CustomEvent("fc_storage_update", {
          detail: { key: "fc_show_loading", value: null },
        }),
      );
    });

    expect(screen.queryByTestId("loading-overlay")).not.toBeInTheDocument();
  });

  it("does not react to FC_ARBITER_TRANSITIONING event (handler removed)", () => {
    render(<GlobalLoadingOverlay />);
    expect(screen.getByTestId("loading-overlay")).toBeInTheDocument();

    act(() => {
      window.dispatchEvent(
        new CustomEvent("fc_storage_update", {
          detail: { key: "fc_arbiter_transitioning", value: "1" },
        }),
      );
    });

    // Should still be visible because FC_ARBITER_TRANSITIONING is no longer handled
    expect(screen.getByTestId("loading-overlay")).toBeInTheDocument();
  });
});
