import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { UploadModal } from "@/components/evidence/UploadModal";

const mockPlaySound = jest.fn();

jest.mock("@/hooks/useSound", () => ({
  useSound: () => ({ playSound: mockPlaySound }),
}));

describe("UploadModal", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("selects a supported file from the file picker", async () => {
    const onFileSelected = jest.fn();
    render(<UploadModal onClose={jest.fn()} onFileSelected={onFileSelected} />);

    fireEvent.change(screen.getByLabelText(/upload evidence file/i), {
      target: {
        files: [new File(["valid"], "evidence.png", { type: "image/png" })],
      },
    });

    expect(screen.getByText(/establishing secure channel/i)).toBeInTheDocument();
    await waitFor(() => expect(onFileSelected).toHaveBeenCalledTimes(1));
    expect(onFileSelected.mock.calls[0][0].name).toBe("evidence.png");
  });

  it("rejects unsupported files before selection", () => {
    const onFileSelected = jest.fn();
    render(<UploadModal onClose={jest.fn()} onFileSelected={onFileSelected} />);

    fireEvent.change(screen.getByLabelText(/upload evidence file/i), {
      target: {
        files: [new File(["bad"], "notes.txt", { type: "text/plain" })],
      },
    });

    expect(screen.getByRole("alert")).toHaveTextContent(/not supported/i);
    expect(onFileSelected).not.toHaveBeenCalled();
    expect(mockPlaySound).toHaveBeenCalledWith("error");
  });
});
