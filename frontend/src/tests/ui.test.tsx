/**
 * UI Tests — Forensic Council Frontend
 * =====================================
 * Tests are based on what is actually rendered by each component.
 * Run: npm test
 */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom";
import Home from "../app/page";
import { useRouter } from "next/navigation";
import { ArcGauge } from "../components/result/ArcGauge";
import { EvidenceThumbnail } from "../components/result/EvidenceThumbnail";
import { ReportFooter } from "../components/result/ReportFooter";

// ── Shared mocks ─────────────────────────────────────────────────────────────

jest.mock("next/navigation", () => ({
  useRouter: jest.fn(),
  usePathname: () => "/",
}));

jest.mock("@/lib/api", () => ({
  autoLoginAsInvestigator: jest.fn().mockResolvedValue({}),
}));

jest.mock("@/lib/pendingFileStore", () => ({
  __pendingFileStore: { file: null },
}));

jest.mock("@/components/evidence/UploadModal", () => ({
  UploadModal: ({
    onFileSelected,
    onClose,
  }: {
    onFileSelected: (file: File) => void;
    onClose: () => void;
  }) => (
    <div role="dialog" aria-label="Upload modal">
      <button
        type="button"
        onClick={() =>
          onFileSelected(new File(["x"], "evidence.jpg", { type: "image/jpeg" }))
        }
      >
        Select File
      </button>
      <button type="button" onClick={onClose}>
        Close
      </button>
    </div>
  ),
}));

jest.mock("@/components/evidence/UploadSuccessModal", () => ({
  UploadSuccessModal: ({
    file,
    onNewUpload,
    onStartAnalysis,
  }: {
    file: File;
    onNewUpload: () => void;
    onStartAnalysis: () => void;
  }) => (
    <div>
      <p>Ready: {file.name}</p>
      <button onClick={onNewUpload}>Upload new file</button>
      <button onClick={onStartAnalysis}>Start Analysis</button>
    </div>
  ),
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

// ── Home page tests ──────────────────────────────────────────────────────────

describe("Home Page", () => {
  const mockPush = jest.fn();

  beforeEach(() => {
    mockPush.mockClear();
    (useRouter as jest.Mock).mockReturnValue({ push: mockPush });
    // Clear sessionStorage between tests
    sessionStorage.clear();
  });

  test("renders the hero heading", () => {
    render(<Home />);
    expect(
      screen.getByText(/Multi Agent Forensic/i),
    ).toBeInTheDocument();
  });

  test("renders 'Evidence Analysis System' in gradient headline", () => {
    render(<Home />);
    expect(screen.getByText(/Evidence Analysis System/i)).toBeInTheDocument();
  });

  test("renders Start Analysis button", () => {
    render(<Home />);
    expect(
      screen.getByRole("button", { name: /Start Analysis/i }),
    ).toBeInTheDocument();
  });

  test("clicking Start Analysis opens the upload modal", () => {
    render(<Home />);
    fireEvent.click(screen.getByRole("button", { name: /Start Analysis/i }));
    expect(screen.getByRole("dialog", { name: /Upload modal/i })).toBeInTheDocument();
  });

  test("selecting a file shows the upload success modal", () => {
    render(<Home />);
    fireEvent.click(screen.getByRole("button", { name: /Start Analysis/i }));
    fireEvent.click(screen.getByRole("button", { name: /Select File/i }));
    expect(screen.getByText(/Ready: evidence\.jpg/i)).toBeInTheDocument();
  });

  test("renders 'How Forensic Council Works' section heading", () => {
    render(<Home />);
    // Heading text is split across spans — find the <h2> by its composite textContent
    const h2 = screen.getAllByRole("heading", { level: 2 }).find((el) =>
      el.textContent?.includes("Forensic Council") && el.textContent?.includes("Works"),
    );
    expect(h2).toBeInTheDocument();
  });

  test("renders 'Meet the Council of Agents' section", () => {
    render(<Home />);
    expect(
      screen.getByText(/Meet the Council of Agents/i),
    ).toBeInTheDocument();
  });

  test("renders all 6 agent cards from AGENTS constant", async () => {
    render(<Home />);
    // Each agent card has its name rendered
    expect(screen.getByText(/Image Forensics/i)).toBeInTheDocument();
    expect(screen.getByText(/Audio Forensics/i)).toBeInTheDocument();
    expect(screen.getByText(/Object Detection/i)).toBeInTheDocument();
    expect(screen.getByText(/Video Forensics/i)).toBeInTheDocument();
    expect(screen.getByText(/Metadata Expert/i)).toBeInTheDocument();
    expect(screen.getByText(/Council Arbiter/i)).toBeInTheDocument();
  });

  test("renders how-it-works steps", () => {
    render(<Home />);
    expect(screen.getByText(/Secure Ingestion/i)).toBeInTheDocument();
    expect(screen.getByText(/Multi-Agent Scan/i)).toBeInTheDocument();
    expect(screen.getByText(/Council Deliberation/i)).toBeInTheDocument();
    expect(screen.getByText(/Cryptographic Verdict/i)).toBeInTheDocument();
  });

  test("clicking close on upload modal dismisses it", () => {
    render(<Home />);
    fireEvent.click(screen.getByRole("button", { name: /Start Analysis/i }));
    expect(screen.getByRole("dialog", { name: /Upload modal/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Close/i }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  test("hero paragraph describes the platform", () => {
    render(<Home />);
    expect(
      screen.getByText(/authenticate digital evidence/i),
    ).toBeInTheDocument();
  });
});

// ── ArcGauge component tests ─────────────────────────────────────────────────

describe("ArcGauge", () => {
  test("renders the numeric value", () => {
    render(<ArcGauge value={75} />);
    expect(screen.getByText("75")).toBeInTheDocument();
  });

  test("renders label when provided", () => {
    render(<ArcGauge value={60} label="Confidence" />);
    expect(screen.getByText("Confidence")).toBeInTheDocument();
  });

  test("renders sublabel when provided", () => {
    render(<ArcGauge value={60} label="Confidence" sublabel="Overall" />);
    expect(screen.getByText("Overall")).toBeInTheDocument();
  });

  test("clamps value to 0–100", () => {
    render(<ArcGauge value={150} />);
    expect(screen.getByText("100")).toBeInTheDocument();
  });

  test("has accessible role=meter", () => {
    render(<ArcGauge value={80} label="Test" />);
    const meter = screen.getByRole("meter");
    expect(meter).toHaveAttribute("aria-valuenow", "80");
    expect(meter).toHaveAttribute("aria-valuemin", "0");
    expect(meter).toHaveAttribute("aria-valuemax", "100");
  });

  test("zero value renders 0", () => {
    render(<ArcGauge value={0} />);
    expect(screen.getByText("0")).toBeInTheDocument();
  });
});

// ── EvidenceThumbnail tests ──────────────────────────────────────────────────

describe("EvidenceThumbnail", () => {
  test("shows image evidence icon when no thumbnail + image mime", () => {
    render(<EvidenceThumbnail thumbnail={null} mimeType="image/jpeg" />);
    expect(screen.getByText(/image evidence/i)).toBeInTheDocument();
  });

  test("shows video evidence icon when no thumbnail + video mime", () => {
    render(<EvidenceThumbnail thumbnail={null} mimeType="video/mp4" />);
    expect(screen.getByText(/video evidence/i)).toBeInTheDocument();
  });

  test("shows audio evidence icon when no thumbnail + audio mime", () => {
    render(<EvidenceThumbnail thumbnail={null} mimeType="audio/wav" />);
    expect(screen.getByText(/audio evidence/i)).toBeInTheDocument();
  });

  test("shows doc evidence icon for unknown mime", () => {
    render(<EvidenceThumbnail thumbnail={null} mimeType={null} />);
    expect(screen.getByText(/doc evidence/i)).toBeInTheDocument();
  });

  test("renders img tag when a thumbnail is provided for an image", () => {
    render(
      <EvidenceThumbnail
        thumbnail="data:image/png;base64,abc"
        mimeType="image/png"
        fileName="test.png"
      />,
    );
    // Use getByAltText to target the <img> specifically (the wrapper div also
    // carries role="img" so getByRole would match two elements)
    const img = screen.getByAltText(/Evidence file: test\.png/i);
    expect(img).toBeInTheDocument();
  });

  test("shows fileName in accessible label", () => {
    render(
      <EvidenceThumbnail
        thumbnail={null}
        mimeType="image/jpeg"
        fileName="evidence.jpg"
      />,
    );
    expect(screen.getByText("evidence.jpg")).toBeInTheDocument();
  });
});

// ── ReportFooter tests ───────────────────────────────────────────────────────

describe("ReportFooter", () => {
  test("renders New Investigation and Back to Home buttons", () => {
    render(<ReportFooter handleNew={jest.fn()} handleHome={jest.fn()} />);
    // Buttons use aria-label as accessible name
    expect(
      screen.getByRole("button", { name: /Start a new forensic investigation/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Return to the home page/i }),
    ).toBeInTheDocument();
  });

  test("calls handleNew when New Investigation is clicked", async () => {
    const handleNew = jest.fn();
    render(<ReportFooter handleNew={handleNew} handleHome={jest.fn()} />);
    await userEvent.click(
      screen.getByRole("button", { name: /Start a new forensic investigation/i }),
    );
    expect(handleNew).toHaveBeenCalledTimes(1);
  });

  test("calls handleHome when Back to Home is clicked", async () => {
    const handleHome = jest.fn();
    render(<ReportFooter handleNew={jest.fn()} handleHome={handleHome} />);
    await userEvent.click(
      screen.getByRole("button", { name: /Return to the home page/i }),
    );
    expect(handleHome).toHaveBeenCalledTimes(1);
  });

  test("footer has accessible landmark role", () => {
    render(<ReportFooter handleNew={jest.fn()} handleHome={jest.fn()} />);
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
  });
});
