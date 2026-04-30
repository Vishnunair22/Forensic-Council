import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { HeroAuthActions } from "@/components/ui/HeroAuthActions";
import { __pendingFileStore } from "@/lib/pendingFileStore";
import { sessionOnlyStorage, storage } from "@/lib/storage";

const mockPush = jest.fn();
const mockPrefetch = jest.fn();
const mockPlaySound = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, prefetch: mockPrefetch }),
}));

jest.mock("@/hooks/useSound", () => ({
  useSound: () => ({ playSound: mockPlaySound }),
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
    sessionOnlyStorage.removeItem("forensic_auto_start");
    sessionOnlyStorage.removeItem("fc_show_loading");
  });

  it("opens the upload modal when the CTA is clicked", () => {
    render(<HeroAuthActions />);

    fireEvent.click(screen.getByRole("button", { name: /upload a file to begin analysis/i }));

    expect(mockPlaySound).toHaveBeenCalledWith("envelope-open");
    expect(screen.getByTestId("upload-modal")).toBeInTheDocument();
  });

  it("starts analysis with a smooth evidence-page handoff", async () => {
    render(<HeroAuthActions />);

    fireEvent.click(screen.getByRole("button", { name: /upload a file to begin analysis/i }));
    fireEvent.click(screen.getByRole("button", { name: /select test file/i }));
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
    render(<HeroAuthActions />);

    fireEvent.click(screen.getByRole("button", { name: /upload a file to begin analysis/i }));
    fireEvent.click(screen.getByRole("button", { name: /select test file/i }));
    fireEvent.click(screen.getByRole("button", { name: /choose another/i }));

    expect(screen.getByTestId("upload-modal")).toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("prefetches the evidence route for a faster handoff", () => {
    render(<HeroAuthActions />);

    expect(mockPrefetch).toHaveBeenCalledWith("/evidence");
  });
});
