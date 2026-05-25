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
  UploadSuccessModal: ({ onStartAnalysis }: { onStartAnalysis: () => void }) => (
    <button data-testid="start-btn" onClick={onStartAnalysis}>Start</button>
  ),
}));

describe("BUG-01 — onStartAnalysis dispatches CustomEvent with correct detail", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    __pendingFileStore.file = null;
    sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
    sessionOnlyStorage.removeItem(STORAGE_KEYS.AUTO_START);
  });

  it("dispatches CustomEvent fc_storage_update with key=FC_SHOW_LOADING and value=true", async () => {
    const events: CustomEvent[] = [];
    const handler = (e: Event) => events.push(e as CustomEvent);
    window.addEventListener("fc_storage_update", handler);

    render(<HeroAuthActions />);
    fireEvent.click(screen.getByRole("button", { name: /upload a file to begin analysis/i }));
    fireEvent.click(screen.getByText("Select File"));
    await act(async () => {
      fireEvent.click(screen.getByTestId("start-btn"));
    });

    const loadingEvents = events.filter(
      (e) => e.detail?.key === STORAGE_KEYS.FC_SHOW_LOADING && e.detail?.value === "true"
    );
    expect(loadingEvents.length).toBeGreaterThanOrEqual(1);
    window.removeEventListener("fc_storage_update", handler);
  });
});

describe("BUG-03 — FC_SHOW_LOADING is not set more than once before router.push", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    __pendingFileStore.file = null;
    sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
  });

  it("sets FC_SHOW_LOADING exactly once before navigation", async () => {
    const setSpy = jest.spyOn(sessionOnlyStorage, "setItem");
    render(<HeroAuthActions />);
    fireEvent.click(screen.getByRole("button", { name: /upload a file to begin analysis/i }));
    fireEvent.click(screen.getByText("Select File"));
    await act(async () => {
      fireEvent.click(screen.getByTestId("start-btn"));
    });

    const loadingWrites = setSpy.mock.calls.filter(
      ([key, value]) => key === STORAGE_KEYS.FC_SHOW_LOADING && value === "true"
    );
    expect(loadingWrites.length).toBe(1);
    setSpy.mockRestore();
  });
});
