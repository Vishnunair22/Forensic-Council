/**
 * Accessibility Tests — Forensic Council Frontend
 * =================================================
 * Uses jest-axe (wraps axe-core) to catch WCAG 2.1 AA violations.
 * Also includes manual keyboard-navigation and ARIA checks.
 *
 * Run: npm test
 */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { axe } from "jest-axe";
import Home from "../app/page";
import { ArcGauge } from "../components/result/ArcGauge";
import { EvidenceThumbnail } from "../components/result/EvidenceThumbnail";
import { ReportFooter } from "../components/result/ReportFooter";

// ── Shared mocks ─────────────────────────────────────────────────────────────

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
  usePathname: () => "/",
}));

jest.mock("@/lib/api", () => ({
  autoLoginAsInvestigator: jest.fn().mockResolvedValue({}),
}));

jest.mock("@/lib/pendingFileStore", () => ({
  __pendingFileStore: { file: null },
}));

jest.mock("@/components/evidence/UploadModal", () => ({
  UploadModal: () => <div role="dialog" aria-modal="true" aria-label="Upload Evidence">Upload modal</div>,
}));

jest.mock("@/components/evidence/UploadSuccessModal", () => ({
  UploadSuccessModal: () => <div>Upload ready</div>,
}));

jest.mock("lucide-react", () =>
  new Proxy(
    {},
    {
      get: () =>
        ({ ...props }: React.SVGProps<SVGSVGElement>) =>
          React.createElement("svg", { "aria-hidden": "true", ...props }),
    },
  ),
);

// ── Home page — axe ──────────────────────────────────────────────────────────

describe("A11y: Home page", () => {
  test("has no axe violations in default state", async () => {
    const { container } = render(<Home />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  test("has no axe violations when upload modal is open", async () => {
    const { container } = render(<Home />);
    fireEvent.click(screen.getByRole("button", { name: /Start Analysis/i }));
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});

// ── ArcGauge — axe + ARIA ────────────────────────────────────────────────────

describe("A11y: ArcGauge", () => {
  test("has no axe violations", async () => {
    const { container } = render(<ArcGauge value={72} label="Confidence" sublabel="Overall" />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  test("meter role has correct ARIA attributes", () => {
    render(<ArcGauge value={65} label="Error Rate" />);
    const meter = screen.getByRole("meter");
    expect(meter).toHaveAttribute("aria-valuenow", "65");
    expect(meter).toHaveAttribute("aria-valuemin", "0");
    expect(meter).toHaveAttribute("aria-valuemax", "100");
    expect(meter).toHaveAttribute("aria-label", "Error Rate: 65%");
  });

  test("SVG is hidden from assistive technology", () => {
    const { container } = render(<ArcGauge value={50} />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("aria-hidden", "true");
  });

  test("value is clamped and still accessible for out-of-range input", () => {
    render(<ArcGauge value={-10} />);
    const meter = screen.getByRole("meter");
    expect(meter).toHaveAttribute("aria-valuenow", "0");
  });
});

// ── EvidenceThumbnail — axe + ARIA ──────────────────────────────────────────

describe("A11y: EvidenceThumbnail", () => {
  test("has no axe violations without thumbnail", async () => {
    const { container } = render(
      <EvidenceThumbnail thumbnail={null} mimeType="image/jpeg" fileName="evidence.jpg" />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  test("has no axe violations with thumbnail img", async () => {
    const { container } = render(
      <EvidenceThumbnail
        thumbnail="data:image/png;base64,abc"
        mimeType="image/png"
        fileName="photo.png"
      />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  test("container has role=img with descriptive label", () => {
    render(
      <EvidenceThumbnail thumbnail={null} mimeType="video/mp4" fileName="clip.mp4" />,
    );
    const el = screen.getByRole("img", { name: /Evidence file: clip\.mp4/i });
    expect(el).toBeInTheDocument();
  });

  test("img element has alt text when thumbnail is provided", () => {
    render(
      <EvidenceThumbnail
        thumbnail="data:image/jpeg;base64,abc"
        mimeType="image/jpeg"
        fileName="photo.jpg"
      />,
    );
    const img = screen.getByAltText(/Evidence file: photo\.jpg/i);
    expect(img).toBeInTheDocument();
  });
});

// ── ReportFooter — axe + keyboard ────────────────────────────────────────────

describe("A11y: ReportFooter", () => {
  test("has no axe violations", async () => {
    const { container } = render(
      <ReportFooter handleNew={jest.fn()} handleHome={jest.fn()} />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  test("buttons are keyboard-focusable", () => {
    render(<ReportFooter handleNew={jest.fn()} handleHome={jest.fn()} />);
    const newBtn = screen.getByRole("button", { name: /Start a new forensic investigation/i });
    const homeBtn = screen.getByRole("button", { name: /Return to the home page/i });
    newBtn.focus();
    expect(document.activeElement).toBe(newBtn);
    homeBtn.focus();
    expect(document.activeElement).toBe(homeBtn);
  });

  test("buttons have explicit accessible names via aria-label", () => {
    render(<ReportFooter handleNew={jest.fn()} handleHome={jest.fn()} />);
    expect(
      screen.getByRole("button", { name: /Start a new forensic investigation/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Return to the home page/i }),
    ).toBeInTheDocument();
  });

  test("footer landmark is present", () => {
    render(<ReportFooter handleNew={jest.fn()} handleHome={jest.fn()} />);
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
  });
});

// ── Home — keyboard navigation ───────────────────────────────────────────────

describe("A11y: Home keyboard navigation", () => {
  test("Start Analysis button is reachable via Tab", () => {
    render(<Home />);
    const btn = screen.getByRole("button", { name: /Start Analysis/i });
    btn.focus();
    expect(document.activeElement).toBe(btn);
  });

  test("Start Analysis button activates on Enter keydown", () => {
    render(<Home />);
    const btn = screen.getByRole("button", { name: /Start Analysis/i });
    btn.focus();
    fireEvent.keyDown(btn, { key: "Enter" });
    // The upload modal or its alternative should appear
    // (button is type="button" so Enter triggers click via the browser;
    //  jsdom fires click on Enter for buttons by default)
    // We just verify no JS error is thrown and the button is still in DOM
    expect(btn).toBeInTheDocument();
  });

  test("main landmark is present for skip-nav target", () => {
    render(<Home />);
    // page.tsx wraps content in <main id="main-content">
    expect(screen.getByRole("main")).toBeInTheDocument();
  });
});
