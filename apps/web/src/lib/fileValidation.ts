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
  const hasAllowedExt = ALLOWED_EXTENSIONS.has(ext);

  let mimeType = file.type;
  if (!mimeType && hasAllowedExt) {
    if (ext === ".jpg" || ext === ".jpeg") mimeType = "image/jpeg";
    else if (ext === ".png") mimeType = "image/png";
    else if (ext === ".webp") mimeType = "image/webp";
    else if (ext === ".tiff" || ext === ".tif") mimeType = "image/tiff";
    else if (ext === ".gif") mimeType = "image/gif";
    else if (ext === ".bmp") mimeType = "image/bmp";
    else if (ext === ".mp4") mimeType = "video/mp4";
    else if (ext === ".mov") mimeType = "video/quicktime";
    else if (ext === ".webm") mimeType = "video/webm";
    else if (ext === ".mkv") mimeType = "video/x-matroska";
    else if (ext === ".avi") mimeType = "video/x-msvideo";
    else if (ext === ".wav") mimeType = "audio/wav";
    else if (ext === ".mp3") mimeType = "audio/mpeg";
    else if (ext === ".m4a") mimeType = "audio/mp4";
    else if (ext === ".flac") mimeType = "audio/flac";
  }

  const hasAllowedMime = !!mimeType && ALLOWED_MIME_TYPES.has(mimeType);

  if (!hasAllowedMime && !hasAllowedExt) {
    return `File type "${file.type || ext || "unknown"}" is not supported.`;
  }

  if (!hasAllowedMime && hasAllowedExt) {
    if (!file.type || file.type === "application/octet-stream" || file.type === "application/x-zip-compressed") {
      return null;
    }
    return `File type "${file.type || "unknown"}" is not recognized. Please verify the file type before upload.`;
  }

  if (hasAllowedMime && !hasAllowedExt) {
    return `File extension "${ext || "unknown"}" does not match content type "${file.type}".`;
  }

  return null;
}
