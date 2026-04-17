import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { HeroAuthActions } from "@/components/ui/HeroAuthActions";
import { __pendingFileStore } from "@/lib/pendingFileStore";
import { storage } from "@/lib/storage";
import { ProtocolWarmingError } from "@/lib/api";

const mockPush = jest.fn();
const mockPlaySound = jest.fn();
const mockCheckBackendHealth = jest.fn();
const mockAutoLoginAsInvestigator = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock("@/hooks/useSound", () => ({
  useSound: () => ({ playSound: mockPlaySound }),
}));

jest.mock("@/lib/api", () => ({
  ProtocolWarmingError: class ProtocolWarmingError extends Error {},
  autoLoginAsInvestigator: (...args: unknown[]) => mockAutoLoginAsInvestigator(...args),
  checkBackendHealth: (...args: unknown[]) => mockCheckBackendHealth(...args),
}));

jest.mock("@/components/ui/ForensicProgressOverlay", () => ({
  ForensicProgressOverlay: ({ title, liveText }: { title: string; liveText: string }) => (
    <div data-testid="progress-overlay">
      <span>{title}</span>
      <span>{liveText}</span>
    </div>
  ),
}));

jest.mock("@/components/evidence/UploadModal", () => ({
  UploadModal: ({
    onClose,
    onFileSelected,
  }: {
    onClose: () => void;
    onFileSelected: (file: File) => void;
  }) => (
    <div data-testid="upload-modal">
      <button onClick={onClose}>Close Upload</button>
      <button
        onClick={() =>
          onFileSelected(new File(["x"], "evidence.jpg", { type: "image/jpeg" }))
        }
      >
        Select Test File
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
    <div data-testid="upload-success-modal">
      <span>{file.name}</span>
      <button onClick={onNewUpload}>Choose Another</button>
      <button onClick={onStartAnalysis}>Start Analysis</button>
    </div>
  ),
}));

describe("HeroAuthActions", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    __pendingFileStore.file = null;
    storage.removeItem("forensic_auto_start");
    storage.removeItem("fc_show_loading");
    storage.removeItem("forensic_auth_ok");
  });

  it("opens the upload modal when the CTA is clicked", () => {
    render(<HeroAuthActions />);

    fireEvent.click(screen.getByRole("button", { name: /upload a file to begin analysis/i }));

    expect(mockPlaySound).toHaveBeenCalledWith("hum");
    expect(screen.getByTestId("upload-modal")).toBeInTheDocument();
  });

  it("starts analysis after healthy backend and demo login", async () => {
    mockCheckBackendHealth.mockResolvedValue({ ok: true });
    mockAutoLoginAsInvestigator.mockResolvedValue({ access_token: "jwt" });

    render(<HeroAuthActions />);

    fireEvent.click(screen.getByRole("button", { name: /upload a file to begin analysis/i }));
    fireEvent.click(screen.getByRole("button", { name: /select test file/i }));
    fireEvent.click(screen.getByRole("button", { name: /start analysis/i }));

    await waitFor(() => {
      expect(mockCheckBackendHealth).toHaveBeenCalled();
      expect(mockAutoLoginAsInvestigator).toHaveBeenCalled();
      expect(mockPush).toHaveBeenCalledWith("/evidence", { scroll: true });
    });

    expect(__pendingFileStore.file?.name).toBe("evidence.jpg");
    expect(storage.getItem("forensic_auto_start")).toBe("true");
    expect(storage.getItem("fc_show_loading")).toBe("true");
    expect(storage.getItem("forensic_auth_ok")).toBe("1");
  });

  it("shows backend warming message and does not navigate when health check fails", async () => {
    mockCheckBackendHealth.mockResolvedValue({
      ok: false,
      warmingUp: true,
      message: "Backend waking up",
    });

    render(<HeroAuthActions />);

    fireEvent.click(screen.getByRole("button", { name: /upload a file to begin analysis/i }));
    fireEvent.click(screen.getByRole("button", { name: /select test file/i }));
    fireEvent.click(screen.getByRole("button", { name: /start analysis/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /protocol warming up/i })).toBeInTheDocument();
    });

    expect(mockAutoLoginAsInvestigator).not.toHaveBeenCalled();
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("handles protocol warming error from auth bootstrap", async () => {
    mockCheckBackendHealth.mockResolvedValue({ ok: true });
    mockAutoLoginAsInvestigator.mockRejectedValue(
      new ProtocolWarmingError("warming"),
    );

    render(<HeroAuthActions />);

    fireEvent.click(screen.getByRole("button", { name: /upload a file to begin analysis/i }));
    fireEvent.click(screen.getByRole("button", { name: /select test file/i }));
    fireEvent.click(screen.getByRole("button", { name: /start analysis/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /protocol warming up/i })).toBeInTheDocument();
    });

    expect(mockPush).not.toHaveBeenCalled();
  });
});
