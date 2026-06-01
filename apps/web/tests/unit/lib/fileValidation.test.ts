import { validateEvidenceFile, ALLOWED_EXTENSIONS } from "@/lib/fileValidation";

function createMockFile(name: string, type: string, size: number): File {
  return new File([new ArrayBuffer(size)], name, { type });
}

describe("validateEvidenceFile", () => {
  describe("valid image files", () => {
    it("accepts JPEG with image/jpeg MIME", () => {
      const file = createMockFile("photo.jpg", "image/jpeg", 1024);
      expect(validateEvidenceFile(file)).toBeNull();
    });

    it("accepts PNG with image/png MIME", () => {
      const file = createMockFile("screenshot.png", "image/png", 2048);
      expect(validateEvidenceFile(file)).toBeNull();
    });

    it("accepts TIFF with image/tiff MIME", () => {
      const file = createMockFile("scan.tiff", "image/tiff", 4096);
      expect(validateEvidenceFile(file)).toBeNull();
    });

    it("accepts WEBP with image/webp MIME", () => {
      const file = createMockFile("image.webp", "image/webp", 1024);
      expect(validateEvidenceFile(file)).toBeNull();
    });

    it("accepts BMP with image/bmp MIME", () => {
      const file = createMockFile("bitmap.bmp", "image/bmp", 512);
      expect(validateEvidenceFile(file)).toBeNull();
    });

    it("accepts GIF with image/gif MIME", () => {
      const file = createMockFile("animation.gif", "image/gif", 8192);
      expect(validateEvidenceFile(file)).toBeNull();
    });
  });

  describe("rejected file types", () => {
    it("rejects audio files", () => {
      const file = createMockFile("recording.mp3", "audio/mpeg", 1024);
      const err = validateEvidenceFile(file);
      expect(err).toContain("not currently supported");
    });

    it("rejects video files", () => {
      const file = createMockFile("video.mp4", "video/mp4", 1024);
      const err = validateEvidenceFile(file);
      expect(err).toContain("not currently supported");
    });

    it("rejects audio/wav files", () => {
      const file = createMockFile("audio.wav", "audio/wav", 1024);
      const err = validateEvidenceFile(file);
      expect(err).toContain("not currently supported");
    });

    it("rejects video/webm files", () => {
      const file = createMockFile("clip.webm", "video/webm", 1024);
      const err = validateEvidenceFile(file);
      expect(err).toContain("not currently supported");
    });
  });

  describe("edge cases", () => {
    it("rejects empty files", () => {
      const file = createMockFile("empty.jpg", "image/jpeg", 0);
      expect(validateEvidenceFile(file)).toBe("File is empty or invalid.");
    });

    it("rejects oversized files", () => {
      const oversized = 55 * 1024 * 1024;
      const file = createMockFile("large.jpg", "image/jpeg", oversized);
      expect(validateEvidenceFile(file)).toBe("File exceeds 50MB limit. Please select a smaller file.");
    });

    it("rejects unknown extensions without MIME", () => {
      const file = createMockFile("document.pdf", "", 1024);
      expect(validateEvidenceFile(file)).toContain("not supported");
    });

    it("handles missing MIME type for known extension", () => {
      const file = createMockFile("photo.jpg", "", 1024);
      expect(validateEvidenceFile(file)).toBeNull();
    });
  });
});

describe("ALLOWED_EXTENSIONS", () => {
  it("only includes image extensions", () => {
    for (const ext of ALLOWED_EXTENSIONS) {
      expect([".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp", ".gif", ".bmp"]).toContain(ext);
    }
  });

  it("does NOT include audio or video extensions", () => {
    expect(ALLOWED_EXTENSIONS.has(".mp3")).toBe(false);
    expect(ALLOWED_EXTENSIONS.has(".wav")).toBe(false);
    expect(ALLOWED_EXTENSIONS.has(".mp4")).toBe(false);
    expect(ALLOWED_EXTENSIONS.has(".avi")).toBe(false);
    expect(ALLOWED_EXTENSIONS.has(".mov")).toBe(false);
    expect(ALLOWED_EXTENSIONS.has(".webm")).toBe(false);
  });
});
