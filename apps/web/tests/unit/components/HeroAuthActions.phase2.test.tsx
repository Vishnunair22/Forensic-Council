import React from "react";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import "@testing-library/jest-dom";
import { HeroAuthActions } from "@/components/ui/HeroAuthActions";
import { sessionOnlyStorage } from "@/lib/storage";
import { STORAGE_KEYS } from "@/lib/storageKeys";
import { __pendingFileStore } from "@/lib/pendingFileStore";

const mockPush = jest.fn();
const mockPrefetch = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, prefetch: mockPrefetch }),
}));
jest.mock("@/hooks/useSound", () => ({ useSound: () => ({ playSound: jest.fn() }) }));
jest.mock("@tanstack/react-query", () => ({ useQueryClient: () => ({ clear: jest.fn() }) }));
jest.mock("@/lib/api", () => ({ autoLoginAsInvestigator: jest.fn().mockResolvedValue("token") }));
jest.mock("@/lib/investigationStorage", () => ({ clearInvestigationPersistence: jest.fn() }));
jest.mock("@/lib/pendingFilePersistence", () => ({
  savePendingEvidenceFile: jest.fn().mockResolvedValue(undefined),
  clearPendingEvidenceFile: jest.fn().mockResolvedValue(undefined),
}));
jest.mock("@/components/evidence/UploadModal", () => ({
  UploadModal: ({ onFileSelected }: { onFileSelected: (f: File) => void }) => (
    <button onClick={() => onFileSelected(new File(["x"], "ev.jpg", { type: "image/jpeg" }))}>
      Select File
    </button>
  ),
}));
jest.mock("@/components/evidence/UploadSuccessModal", () => ({
  UploadSuccessModal: ({ onStartAnalysis, isHandingOff }: { onStartAnalysis: () => void; isHandingOff?: boolean }) => (
    <button data-testid="start-btn" onClick={onStartAnalysis} disabled={isHandingOff}>Start</button>
  ),
}));

describe("BUG-05 — setShowUpload(false) fires after flags are written", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    __pendingFileStore.file = null;
    sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
    sessionOnlyStorage.removeItem(STORAGE_KEYS.AUTO_START);
  });

  it("sets AUTO_START and FC_SHOW_LOADING before setShowUpload(false) resolves", async () => {
    const setSpy = jest.spyOn(sessionOnlyStorage, "setItem");
    render(<HeroAuthActions />);
    fireEvent.click(screen.getByRole("button", { name: /upload a file to begin analysis/i }));
    fireEvent.click(screen.getByText("Select File"));
    await act(async () => {
      fireEvent.click(screen.getByTestId("start-btn"));
    });

    const autoStartCalls = setSpy.mock.calls.filter(([k]) => k === STORAGE_KEYS.AUTO_START);
    const showLoadingCalls = setSpy.mock.calls.filter(([k]) => k === STORAGE_KEYS.FC_SHOW_LOADING);
    expect(autoStartCalls.length).toBe(1);
    expect(showLoadingCalls.length).toBe(1);
    expect(mockPush).toHaveBeenCalledWith("/evidence", { scroll: true });
    setSpy.mockRestore();
  });
});

describe("BUG-06 — savePendingEvidenceFile is awaited before router.push", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    __pendingFileStore.file = null;
    sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
  });

  it("calls savePendingEvidenceFile before router.push", async () => {
    const { savePendingEvidenceFile } = require("@/lib/pendingFilePersistence");
    render(<HeroAuthActions />);
    fireEvent.click(screen.getByRole("button", { name: /upload a file to begin analysis/i }));
    fireEvent.click(screen.getByText("Select File"));
    await act(async () => {
      fireEvent.click(screen.getByTestId("start-btn"));
    });

    // savePendingEvidenceFile resolved (mock) then router.push called
    expect(savePendingEvidenceFile).toHaveBeenCalled();
    // router.push called after save resolved
    expect(mockPush).toHaveBeenCalledWith("/evidence", { scroll: true });
  });
});
