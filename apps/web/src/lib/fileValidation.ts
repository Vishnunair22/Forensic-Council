import { ALLOWED_MIME_TYPES, MAX_UPLOAD_SIZE_BYTES } from "@/lib/constants";

export const ALLOWED_EXTENSIONS = new Set([
  ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp", ".gif", ".bmp",
]);

export function getFileExtension(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLowerCase() : "";
}

export interface ValidationError {
  code: "EMPTY_FILE" | "SIZE_EXCEEDED" | "INVALID_EXTENSION" | "INVALID_MIME" | "EXTENSION_MISMATCH";
  message: string;
}

export function validateEvidenceFile(file: File): string | null {
  if (file.size <= 0) {
    return "File is empty or invalid.";
  }

  if (file.size > MAX_UPLOAD_SIZE_BYTES) {
    return "File exceeds 50MB limit. Please select a smaller file.";
  }

  const ext = getFileExtension(file.name);
  const hasAllowedExt = ALLOWED_EXTENSIONS.has(ext);

  let mimeType = file.type;
  if (!mimeType && hasAllowedExt) {
    if (ext === ".jpg" || ext === ".jpeg") mimeType = "image/jpeg";
    else if (ext === ".png") mimeType = "image/png";
    else if (ext === ".webp") mimeType = "image/webp";
    else if (ext === ".tiff" || ext === ".tif") mimeType = "image/tiff";
    else if (ext === ".gif") mimeType = "image/gif";
    else if (ext === ".bmp") mimeType = "image/bmp";
  }

  const hasAllowedMime = !!mimeType && ALLOWED_MIME_TYPES.has(mimeType);

  if (!hasAllowedMime && !hasAllowedExt) {
    return `File type "${file.type || ext || "unknown"}" is not supported. Accepted: Images (JPG, PNG, TIFF, WEBP, GIF, BMP).`;
  }

  if (!hasAllowedMime && hasAllowedExt) {
    if (!file.type || file.type === "application/octet-stream" || file.type === "application/x-zip-compressed") {
      return null;
    }
    return `File type "${file.type}" does not match extension "${ext}". Please verify the file is not corrupted.`;
  }

  if (hasAllowedMime && !hasAllowedExt) {
    return `File extension "${ext}" does not match content type "${file.type}". Rename the file or select a different file.`;
  }

  return null;
}

export function getValidationErrorCode(file: File): ValidationError | null {
  if (file.size <= 0) {
    return { code: "EMPTY_FILE", message: "File is empty or invalid." };
  }

  if (file.size > MAX_UPLOAD_SIZE_BYTES) {
    return { code: "SIZE_EXCEEDED", message: "File exceeds 50MB limit." };
  }

  const ext = getFileExtension(file.name);
  const hasAllowedExt = ALLOWED_EXTENSIONS.has(ext);
  const hasAllowedMime = file.type ? ALLOWED_MIME_TYPES.has(file.type) : false;

  if (!hasAllowedExt && !hasAllowedMime) {
    return {
      code: "INVALID_EXTENSION",
      message: `File type "${file.type || ext || "unknown"}" is not supported.`,
    };
  }

  if (hasAllowedExt && !hasAllowedMime && file.type && file.type !== "application/octet-stream") {
    return {
      code: "EXTENSION_MISMATCH",
      message: `Extension "${ext}" does not match content type "${file.type}".`,
    };
  }

  return null;
}
