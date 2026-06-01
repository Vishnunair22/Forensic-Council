import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { ReportIntegrity } from "@/components/result/ReportIntegrity";
import type { ReportDTO } from "@/lib/api";

const mockReport: ReportDTO = {
  report_id: "report-abc-123",
  session_id: "session-xyz-789",
  case_id: "case-456",
  overall_verdict: "AUTHENTIC",
  overall_confidence: 0.95,
  report_hash: "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b",
  cryptographic_signature: "MEQCIH0AoM7N4kqL1xJ2yZ3w4B5r6T7y8U9i0O1p2A3s4D5f6G7h8J9k0L1m2N3",
  signed_utc: "2025-06-01T12:00:00Z",
  is_deep_analysis: false,
};

describe("ReportIntegrity", () => {
  it("renders report hash and ECDSA signature as separate fields", () => {
    render(<ReportIntegrity report={mockReport} sessionId="session-xyz-789" isDeepPhase={false} />);

    expect(screen.getByText("Report Hash (SHA-256)")).toBeInTheDocument();
    expect(screen.getByText("ECDSA Signature")).toBeInTheDocument();
  });

  it("displays the full report hash", () => {
    render(<ReportIntegrity report={mockReport} sessionId="session-xyz-789" isDeepPhase={false} />);

    expect(screen.getByText(mockReport.report_hash!)).toBeInTheDocument();
  });

  it("displays the full ECDSA signature", () => {
    render(<ReportIntegrity report={mockReport} sessionId="session-xyz-789" isDeepPhase={false} />);

    expect(screen.getByText(mockReport.cryptographic_signature!)).toBeInTheDocument();
  });

  it("shows 'Verified' badge when both hash and signature are present", () => {
    render(<ReportIntegrity report={mockReport} sessionId="session-xyz-789" isDeepPhase={false} />);

    expect(screen.getByText("Verified")).toBeInTheDocument();
  });

  it("shows dev-mode message when both hash and signature are missing", () => {
    const noSigReport: ReportDTO = {
      ...mockReport,
      report_hash: undefined,
      cryptographic_signature: undefined,
    };
    render(<ReportIntegrity report={noSigReport} sessionId="session-xyz-789" isDeepPhase={false} />);

    expect(screen.getByText("Signed key store unavailable in development")).toBeInTheDocument();
  });

  it("has separate copy buttons for hash and signature", () => {
    render(<ReportIntegrity report={mockReport} sessionId="session-xyz-789" isDeepPhase={false} />);

    const copyButtons = screen.getAllByRole("button", { name: /copy/i });
    expect(copyButtons.length).toBe(2);
  });

  it("shows deep analysis phase label when isDeepPhase is true", () => {
    render(<ReportIntegrity report={mockReport} sessionId="session-xyz-789" isDeepPhase={true} />);

    expect(screen.getByText("Deep Analysis")).toBeInTheDocument();
  });

  it("shows initial analysis phase label when isDeepPhase is false", () => {
    render(<ReportIntegrity report={mockReport} sessionId="session-xyz-789" isDeepPhase={false} />);

    expect(screen.getByText("Initial Analysis")).toBeInTheDocument();
  });
});
