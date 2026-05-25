import React from "react";
import { render } from "@testing-library/react";
import "@testing-library/jest-dom";

const mockMotionDiv = jest.fn((props: React.PropsWithChildren<Record<string, unknown>>) =>
  React.createElement("div", props, props.children)
);

jest.mock("framer-motion", () => ({
  motion: {
    div: (props: React.PropsWithChildren<Record<string, unknown>>) => mockMotionDiv(props),
  },
  useReducedMotion: () => false,
}));
jest.mock("@/hooks/useSound", () => ({
  useSound: () => ({ playSound: jest.fn() }),
}));
jest.mock("@/components/result/ResultLayout", () => ({
  ResultLayout: () => React.createElement("div", { "data-testid": "result-layout" }),
}));

describe("BUG-23 — DynamicResultClient motion animation has no delay", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders motion wrapper with immediate animation (no delay)", () => {
    const { container } = render(
      React.createElement(
        require("@/components/pages/DynamicResultClient").DynamicResultClient,
        { sessionId: "test-session" },
      ),
    );
    expect(container.querySelector("[data-testid='result-layout']")).toBeInTheDocument();
  });

  it("uses duration 0.45 and no delay in transition", () => {
    render(
      React.createElement(
        require("@/components/pages/DynamicResultClient").DynamicResultClient,
        { sessionId: "test-session" },
      ),
    );

    const callProps = mockMotionDiv.mock.calls[0][0];
    const transition = callProps.transition;
    expect(transition).toBeDefined();
    expect(transition.duration).toBe(0.45);
    expect(transition.delay).toBeUndefined();
  });
});
