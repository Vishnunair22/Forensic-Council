import { ALLOWED_MIME_TYPES, MAX_UPLOAD_SIZE_BYTES } from "@/lib/constants";

export const ALLOWED_EXTENSIONS = new Set([
  // Images
  ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp", ".gif", ".bmp",
  // Audio
  ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a",
  // Video
  ".mp4", ".m4v", ".mpeg", ".mpg", ".webm", ".mov", ".avi", ".mkv",
  // Documents
  ".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".csv", ".md",
]);

/** Map from extension to authoritative MIME — mirrors backend _EXTENSION_MAP. */
const EXT_TO_MIME: Record<string, string> = {
  // Images
  ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".tif": "image/tiff", ".tiff": "image/tiff",
  ".webp": "image/webp",
  ".gif": "image/gif",
  ".bmp": "image/bmp",
  // Audio
  ".mp3": "audio/mpeg",
  ".wav": "audio/wav",
  ".flac": "audio/flac",
  ".aac": "audio/aac",
  ".ogg": "audio/ogg",
  ".m4a": "audio/x-m4a",
  // Video
  ".mp4": "video/mp4", ".m4v": "video/mp4",
  ".mpeg": "video/mpeg", ".mpg": "video/mpeg",
  ".webm": "video/webm",
  ".mov": "video/quicktime",
  ".avi": "video/x-msvideo",
  ".mkv": "video/x-matroska",
  // Documents
  ".pdf": "application/pdf",
  ".doc": "application/msword",
  ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  ".odt": "application/vnd.oasis.opendocument.text",
  ".rtf": "application/rtf",
  ".txt": "text/plain",
  ".csv": "text/csv",
  ".md": "text/markdown",
};

export function getFileExtension(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLowerCase() : "";
}

/** Derive a human-readable category label from MIME type. */
export function getFileCategory(mime: string): "image" | "audio" | "video" | "document" | "unknown" {
  if (mime.startsWith("image/")) return "image";
  if (mime.startsWith("audio/")) return "audio";
  if (mime.startsWith("video/")) return "video";
  if (
    mime === "application/pdf" ||
    mime === "application/msword" ||
    mime === "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
    mime === "application/vnd.oasis.opendocument.text" ||
    mime === "application/rtf" ||
    mime === "text/rtf" ||
    mime.startsWith("text/")
  ) return "document";
  return "unknown";
}

/**
 * Resolve the effective MIME type for a file, preferring a reliable
 * extension-based lookup when the browser reports an empty or generic type.
 * This is what agent filtering should use — the raw `file.type` is often
 * empty for audio/video, which would falsely show agents as "not applicable"
 * before the backend's libmagic detection corrects it.
 */
export function resolveMimeType(file: File): string {
  const mime = file.type;
  const generic =
    !mime ||
    mime === "application/octet-stream" ||
    mime === "application/x-zip-compressed";
  if (generic) {
    const ext = getFileExtension(file.name);
    return EXT_TO_MIME[ext] ?? mime ?? "";
  }
  return mime;
}

export function validateEvidenceFile(file: File): string | null {
  if (file.size <= 0) {
    return "File is empty or invalid.";
  }

  if (file.size > MAX_UPLOAD_SIZE_BYTES) {
    return "File exceeds 50 MB limit. Please select a smaller file.";
  }

  const ext = getFileExtension(file.name);
  const hasAllowedExt = ALLOWED_EXTENSIONS.has(ext);

  // Resolve MIME: use the browser-reported type when present, fall back to
  // extension lookup when the browser reports an empty or generic type.
  let mimeType = file.type;
  const isGenericMime =
    !mimeType ||
    mimeType === "application/octet-stream" ||
    mimeType === "application/x-zip-compressed";

  if (isGenericMime && hasAllowedExt) {
    mimeType = EXT_TO_MIME[ext] ?? "";
  }

  const hasAllowedMime = !!mimeType && ALLOWED_MIME_TYPES.has(mimeType);

  if (!hasAllowedMime && !hasAllowedExt) {
    return (
      `File type "${file.type || ext || "unknown"}" is not supported. ` +
      `Accepted: Images (JPG PNG TIFF WEBP GIF BMP), Audio (MP3 WAV FLAC AAC OGG M4A), ` +
      `Video (MP4 WEBM MOV AVI MKV), Documents (PDF DOC DOCX ODT RTF TXT CSV MD).`
    );
  }

  // Extension/MIME mismatch detection — only when both are resolved.
  if (hasAllowedMime && hasAllowedExt) {
    const expectedFromExt = EXT_TO_MIME[ext];
    // Allow if MIME prefix matches (catches audio/wav vs audio/x-wav, etc.)
    const mimePrefix = mimeType.split("/")[0];
    const expectedPrefix = expectedFromExt?.split("/")[0];
    if (
      expectedFromExt &&
      expectedFromExt !== mimeType &&
      mimePrefix !== expectedPrefix
    ) {
      return `File extension "${ext}" doesn't match content type "${mimeType}". Verify the file is not corrupted.`;
    }
  }

  if (!hasAllowedMime && hasAllowedExt) {
    // If the browser reports a non-generic foreign type for a known extension,
    // flag it so the user knows the file may be misidentified.
    if (!isGenericMime) {
      return `File type "${mimeType}" does not match extension "${ext}". Verify the file is not corrupted.`;
    }
  }

  if (hasAllowedMime && !hasAllowedExt) {
    return `File extension "${ext}" does not match content type "${mimeType}". Rename the file or select a different one.`;
  }

  return null;
}
