import React from "react";
import { render } from "@testing-library/react";
import "@testing-library/jest-dom";
import { axe } from "jest-axe";
import Home from "../app/page";

// Mock next/navigation
jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: jest.fn(),
  }),
}));

jest.mock("@/components/evidence/UploadModal", () => ({
  UploadModal: () => <div>Upload modal</div>,
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

describe("A11y Tests", () => {
  test("Home page should have no basic accessibility violations", async () => {
    const { container } = render(<Home />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
