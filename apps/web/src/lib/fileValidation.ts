import { ALLOWED_MIME_TYPES, MAX_UPLOAD_SIZE_BYTES } from "@/lib/constants";

export const ALLOWED_EXTENSIONS = new Set([
  ".jpg",
  ".jpeg",
  ".png",
  ".tiff",
  ".tif",
  ".webp",
  ".gif",
  ".bmp",
  ".mp4",
  ".mov",
  ".avi",
  ".wav",
  ".mp3",
  ".m4a",
  ".flac",
]);

export function getFileExtension(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLowerCase() : "";
}

export function validateEvidenceFile(file: File): string | null {
  if (file.size > MAX_UPLOAD_SIZE_BYTES) {
    return "File exceeds 50MB limit.";
  }

  const ext = getFileExtension(file.name);
  const hasAllowedMime = !!file.type && ALLOWED_MIME_TYPES.has(file.type);
  const hasAllowedExt = ALLOWED_EXTENSIONS.has(ext);

  if (!hasAllowedMime && !hasAllowedExt) {
    return `File type "${file.type || ext || "unknown"}" is not supported.`;
  }

  return null;
}
