import { getFileCategory, resolveMimeType, validateEvidenceFile, ALLOWED_EXTENSIONS } from "@/lib/fileValidation";

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

  describe("valid audio, video, and document files (multi-modal)", () => {
    it("accepts MP3 audio", () => {
      expect(validateEvidenceFile(createMockFile("recording.mp3", "audio/mpeg", 1024))).toBeNull();
    });

    it("accepts WAV audio", () => {
      expect(validateEvidenceFile(createMockFile("audio.wav", "audio/wav", 1024))).toBeNull();
    });

    it("accepts MP4 video", () => {
      expect(validateEvidenceFile(createMockFile("video.mp4", "video/mp4", 1024))).toBeNull();
    });

    it("accepts MP4-family files reported as generic application/mp4", () => {
      expect(validateEvidenceFile(createMockFile("video.mp4", "application/mp4", 1024))).toBeNull();
      expect(validateEvidenceFile(createMockFile("audio.m4a", "application/mp4", 1024))).toBeNull();
      expect(getFileCategory("application/mp4")).toBe("video");
      expect(resolveMimeType(createMockFile("audio.m4a", "application/mp4", 1024))).toBe("audio/x-m4a");
      expect(resolveMimeType(createMockFile("video.mp4", "application/mp4", 1024))).toBe("video/mp4");
    });

    it("accepts WEBM video", () => {
      expect(validateEvidenceFile(createMockFile("clip.webm", "video/webm", 1024))).toBeNull();
    });

    it("accepts PDF documents", () => {
      expect(validateEvidenceFile(createMockFile("report.pdf", "application/pdf", 1024))).toBeNull();
    });

    it("accepts backend-supported text and office documents", () => {
      expect(validateEvidenceFile(createMockFile("notes.txt", "text/plain", 1024))).toBeNull();
      expect(validateEvidenceFile(createMockFile("brief.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", 1024))).toBeNull();
      expect(validateEvidenceFile(createMockFile("evidence.rtf", "application/rtf", 1024))).toBeNull();
      expect(validateEvidenceFile(createMockFile("table.csv", "text/csv", 1024))).toBeNull();
    });

    it("rejects a genuinely unsupported type", () => {
      const err = validateEvidenceFile(createMockFile("archive.zip", "application/zip", 1024));
      expect(err).toContain("not supported");
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
      expect(validateEvidenceFile(file)).toBe("File exceeds 50 MB limit. Please select a smaller file.");
    });

    it("rejects unknown extensions without MIME", () => {
      const file = createMockFile("document.xyz", "", 1024);
      expect(validateEvidenceFile(file)).toContain("not supported");
    });

    it("handles missing MIME type for known extension", () => {
      const file = createMockFile("photo.jpg", "", 1024);
      expect(validateEvidenceFile(file)).toBeNull();
    });
  });
});

describe("ALLOWED_EXTENSIONS (multi-modal)", () => {
  it("includes image, audio, video, and document extensions", () => {
    for (const ext of [".jpg", ".png", ".tiff", ".webp", ".gif", ".bmp"]) {
      expect(ALLOWED_EXTENSIONS.has(ext)).toBe(true);
    }
    for (const ext of [".mp3", ".wav", ".flac", ".m4a"]) {
      expect(ALLOWED_EXTENSIONS.has(ext)).toBe(true);
    }
    for (const ext of [".mp4", ".webm", ".mov", ".avi", ".mkv"]) {
      expect(ALLOWED_EXTENSIONS.has(ext)).toBe(true);
    }
    for (const ext of [".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".csv", ".md"]) {
      expect(ALLOWED_EXTENSIONS.has(ext)).toBe(true);
    }
  });

  it("excludes genuinely unsupported types", () => {
    expect(ALLOWED_EXTENSIONS.has(".zip")).toBe(false);
    expect(ALLOWED_EXTENSIONS.has(".exe")).toBe(false);
  });
});
