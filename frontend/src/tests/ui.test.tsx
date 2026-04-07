/**
 * UI Tests — Forensic Council Frontend
 * =====================================
 * Tests for modern component structures and interactions.
 *
 * Run: npm test
 */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import Home from "../app/page";
import { ArcGauge } from "../components/result/ArcGauge";
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
          React.createElement("svg", { "data-testid": "icon", ...props }),
    },
  ),
);

// ── Home Page tests ──────────────────────────────────────────────────────────

describe("UI: Home Page", () => {
  test("renders the primary mission heading", () => {
    render(<Home />);
    expect(screen.getByText(/Multi Agent Forensic/i)).toBeInTheDocument();
  });

  test("renders Start Analysis call-to-action", () => {
    render(<Home />);
    expect(screen.getByRole("button", { name: /Access Forensic Core/i })).toBeInTheDocument();
  });
});

// ── ArcGauge component tests ─────────────────────────────────────────────────

describe("UI: ArcGauge", () => {
  test("renders the numeric value correctly", () => {
    render(<ArcGauge value={85} />);
    expect(screen.getByText("85")).toBeInTheDocument();
  });

  test("renders labels and sublabels", () => {
    render(<ArcGauge value={60} label="Trust" sublabel="Weighted" />);
    expect(screen.getByText("Trust")).toBeInTheDocument();
    expect(screen.getByText("Weighted")).toBeInTheDocument();
  });

  test("clamps values outside 0-100 range", () => {
    render(<ArcGauge value={120} />);
    expect(screen.getByText("100")).toBeInTheDocument();
  });
});

// ── AgentFindingCard component tests ─────────────────────────────────────────

describe("UI: AgentFindingCard", () => {
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
        reasoning_summary: "Signal authentic.",
        metadata: { tool_name: "ela_full_image", execution_time_ms: 120 }
      }
    ],
    deepFindings: [],
    metrics: { confidence_score: 0.95, total_tools_called: 1, tools_succeeded: 1 },
    narrative: "Image integrity verified.",
    phase: "initial",
    defaultOpen: false
  };

  test("renders Agent name and role from metadata", () => {
    render(<AgentFindingCard {...mockProps} />);
    expect(screen.getByText(/Agent 01/i)).toBeInTheDocument();
    expect(screen.getByText(/Visual Integrity/i)).toBeInTheDocument();
  });

  test("renders the confidence percentage from metrics", () => {
    render(<AgentFindingCard {...mockProps} />);
    const elements = screen.getAllByText("95%");
    expect(elements.length).toBeGreaterThan(0);
  });

  test("expanding show findings and narrative", () => {
    render(<AgentFindingCard {...mockProps} />);
    const header = screen.getByRole("button", { name: /Agent 01/i });
    fireEvent.click(header);
    expect(screen.getByText(/Image integrity verified/i)).toBeInTheDocument();
    expect(screen.getByText(/Ela Full Image/i)).toBeInTheDocument();
  });

  test("renders timing metadata correctly", () => {
    render(<AgentFindingCard {...mockProps} defaultOpen />);
    expect(screen.getByText("120ms")).toBeInTheDocument();
  });
});
