import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { HeroAuthActions } from "@/components/ui/HeroAuthActions";
import { GlobalLoadingOverlay } from "@/components/ui/GlobalLoadingOverlay";
import { __pendingFileStore } from "@/lib/pendingFileStore";
import { sessionOnlyStorage, storage } from "@/lib/storage";

const mockPush = jest.fn();
const mockPrefetch = jest.fn();
const mockPlaySound = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, prefetch: mockPrefetch }),
  usePathname: () => "/",
}));

jest.mock("@/hooks/useSound", () => ({
  useSound: () => ({ playSound: mockPlaySound }),
}));

jest.mock("@/lib/pendingFilePersistence", () => ({
  savePendingEvidenceFile: jest.fn().mockResolvedValue(undefined),
}));

jest.mock("@/lib/crypto/fileHash", () => ({
  computeFileSha256: jest.fn(() => Promise.resolve({ hex: "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890" })),
}));

jest.mock("@tanstack/react-query", () => ({
  useQueryClient: jest.fn(() => ({
    clear: jest.fn(),
  })),
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
    onDismiss,
    onStartAnalysis,
    isHandingOff,
    authError,
  }: {
    file: File;
    onDismiss: () => void;
    onStartAnalysis: () => void;
    isHandingOff?: boolean;
    authError?: string | null;
  }) => (
    <div data-testid="upload-success-modal">
      <span>{file.name}</span>
      {authError && <div role="alert">{authError}</div>}
      <button onClick={onDismiss}>Choose Another</button>
      <button onClick={onStartAnalysis} disabled={isHandingOff}>
        {isHandingOff ? "Initializing Agents..." : "Start Analysis"}
      </button>
    </div>
  ),
}));

const renderWithOverlay = () => render(
  <>
    <HeroAuthActions />
    <GlobalLoadingOverlay />
  </>
);

describe("HeroAuthActions", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    __pendingFileStore.file = null;
    __pendingFileStore.authPromise = null;
    __pendingFileStore.authError = null;
    storage.removeItem("forensic_auto_start");
    storage.removeItem("fc_show_loading");
    storage.removeItem("forensic_auth_ok");
    sessionOnlyStorage.removeItem("forensic_auto_start");
    sessionOnlyStorage.removeItem("fc_show_loading");
  });

  it("opens the upload modal when the CTA is clicked", () => {
    renderWithOverlay();

    fireEvent.click(screen.getByRole("button", { name: /upload a file to begin analysis/i }));

    expect(mockPlaySound).toHaveBeenCalledWith("envelope-open");
    expect(screen.getByTestId("upload-modal")).toBeInTheDocument();
  });

  it("starts analysis with a smooth evidence-page handoff", async () => {
    renderWithOverlay();

    fireEvent.click(screen.getByRole("button", { name: /upload a file to begin analysis/i }));
    fireEvent.click(screen.getByRole("button", { name: /select test file/i }));

    // Flush microtasks so the async SHA-256 hash computation resolves before we click start
    await act(async () => {});
    fireEvent.click(screen.getByRole("button", { name: /start analysis/i }));

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/evidence", { scroll: true });
    });

    expect(__pendingFileStore.file?.name).toBe("evidence.jpg");
    expect(sessionOnlyStorage.getItem("forensic_auto_start")).toBe("true");
    expect(sessionOnlyStorage.getItem("fc_show_loading")).toBe("true");
    expect(screen.getByText(/opening evidence analysis/i)).toBeInTheDocument();
  });

  it("lets users choose another file before starting", () => {
    renderWithOverlay();

    fireEvent.click(screen.getByRole("button", { name: /upload a file to begin analysis/i }));
    fireEvent.click(screen.getByRole("button", { name: /select test file/i }));
    fireEvent.click(screen.getByRole("button", { name: /choose another/i }));

    expect(screen.getByTestId("upload-modal")).toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("does not get stuck handing off when auth already failed", async () => {
    renderWithOverlay();

    fireEvent.click(screen.getByRole("button", { name: /upload a file to begin analysis/i }));
    fireEvent.click(screen.getByRole("button", { name: /select test file/i }));

    __pendingFileStore.authPromise = null;
    __pendingFileStore.authError = new Error("Demo auth unavailable");
    fireEvent.click(screen.getByRole("button", { name: /start analysis/i }));

    await waitFor(() => {
      expect(mockPush).not.toHaveBeenCalled();
      expect(screen.getByRole("button", { name: /start analysis/i })).toBeEnabled();
    });
    expect(__pendingFileStore.file).toBeNull();
    expect(sessionOnlyStorage.getItem("forensic_auto_start")).toBeNull();
  });

  it("prefetches the evidence route for a faster handoff", () => {
    renderWithOverlay();

    expect(mockPrefetch).toHaveBeenCalledWith("/evidence");
  });
});
