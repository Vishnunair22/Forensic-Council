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
import { AgentFindingCard } from "../components/ui/AgentFindingCard";

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
  test("has no axe violations", async () => {
    const { container } = render(<Home />);
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
    expect(meter).toHaveAttribute("aria-label", "Error Rate: 65%");
  });
});

// ── EvidenceThumbnail — axe + ARIA ──────────────────────────────────────────

describe("A11y: EvidenceThumbnail", () => {
  test("has no axe violations", async () => {
    const { container } = render(
      <EvidenceThumbnail thumbnail={null} mimeType="image/jpeg" fileName="evidence.jpg" />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  test("container has role=img with descriptive label", () => {
    render(<EvidenceThumbnail thumbnail={null} mimeType="video/mp4" fileName="clip.mp4" />);
    const el = screen.getByRole("img", { name: /Evidence file: clip\.mp4/i });
    expect(el).toBeInTheDocument();
  });
});

// ── AgentFindingCard — keyboard + ARIA ───────────────────────────────────────

describe("A11y: AgentFindingCard", () => {
  const mockProps: any = {
    agentId: "Agent1",
    initialFindings: [
      {
        agent_id: "Agent1",
        finding_id: "f1",
        finding_type: "ela_full_image",
        status: "CONFIRMED",
        raw_confidence_score: 0.95,
        confidence_raw: 0.95,
        calibrated: true,
        agent_name: "Agent 01",
        reasoning_summary: "No splicing detected.",
        metadata: { tool_name: "ela_full_image" }
      }
    ],
    deepFindings: [],
    metrics: { confidence_score: 0.95, total_tools_called: 1, tools_succeeded: 1 },
    narrative: "Image integrity verified via ELA.",
    phase: "initial"
  };

  test("main card button is keyboard-focusable", () => {
    render(<AgentFindingCard {...mockProps} />);
    const btn = screen.getByRole("button", { name: /Agent 01/i });
    btn.focus();
    expect(document.activeElement).toBe(btn);
  });

  test("expanding card updates aria-expanded state", () => {
    render(<AgentFindingCard {...mockProps} />);
    const btn = screen.getByRole("button", { name: /Agent 01/i });
    expect(btn).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(btn);
    expect(btn).toHaveAttribute("aria-expanded", "true");
  });

  test("tool rows within expanded card are focusable", () => {
    render(<AgentFindingCard {...mockProps} defaultOpen />);
    const toolBtn = screen.getByRole("button", { name: /Ela Full Image/i });
    toolBtn.focus();
    expect(document.activeElement).toBe(toolBtn);
  });
});

// ── ReportFooter — axe + landmark ────────────────────────────────────────────

describe("A11y: ReportFooter", () => {
  test("has no axe violations", async () => {
    const { container } = render(<ReportFooter handleNew={jest.fn()} handleHome={jest.fn()} />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  test("footer landmark is present", () => {
    render(<ReportFooter handleNew={jest.fn()} handleHome={jest.fn()} />);
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
  });
});
