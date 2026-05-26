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
  ".mkv",
  ".webm",
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
  if (file.size <= 0) {
    return "File is empty or invalid.";
  }

  if (file.size > MAX_UPLOAD_SIZE_BYTES) {
    return "File exceeds 50MB limit.";
  }

  const ext = getFileExtension(file.name);
  const hasAllowedMime = !!file.type && ALLOWED_MIME_TYPES.has(file.type);
  const hasAllowedExt = ALLOWED_EXTENSIONS.has(ext);

  if (!hasAllowedMime && !hasAllowedExt) {
    return `File type "${file.type || ext || "unknown"}" is not supported.`;
  }

  if (!hasAllowedMime && hasAllowedExt) {
    return `File type "${file.type || "unknown"}" is not recognized. Please verify the file type before upload.`;
  }

  if (hasAllowedMime && !hasAllowedExt) {
    return `File extension "${ext || "unknown"}" does not match content type "${file.type}".`;
  }

  return null;
}
