import { ALLOWED_MIME_TYPES, MAX_UPLOAD_SIZE_BYTES } from "@/lib/constants";
import { ALLOWED_EXTENSIONS, getFileExtension } from "@/lib/fileValidation";

export interface ValidationResult {
  valid: boolean;
  error?: {
    code: "SIZE_EXCEEDED" | "EMPTY_FILE" | "INVALID_TYPE" | "EXTENSION_MISMATCH" | "TYPE_UNKNOWN";
    message: string;
  };
}

export class FileValidationService {
  validate(file: File): ValidationResult {
    if (file.size <= 0) {
      return {
        valid: false,
        error: { code: "EMPTY_FILE", message: "File is empty or invalid." },
      };
    }

    if (file.size > MAX_UPLOAD_SIZE_BYTES) {
      return {
        valid: false,
        error: { code: "SIZE_EXCEEDED", message: "File exceeds 50MB limit." },
      };
    }

    const ext = getFileExtension(file.name);
    const hasAllowedExt = ALLOWED_EXTENSIONS.has(ext);
    const hasAllowedMime = file.type ? ALLOWED_MIME_TYPES.has(file.type) : false;

    if (!hasAllowedExt && !hasAllowedMime) {
      return {
        valid: false,
        error: {
          code: "INVALID_TYPE",
          message: `File type "${file.type || ext || "unknown"}" is not supported. Accepted formats: Images (JPG, PNG, TIFF, WEBP, GIF, BMP), Video (MP4, MOV, AVI, MKV, WEBM), Audio (WAV, MP3, M4A, FLAC).`,
        },
      };
    }

    if (hasAllowedExt && !hasAllowedMime && file.type && file.type !== "application/octet-stream") {
      return {
        valid: false,
        error: {
          code: "EXTENSION_MISMATCH",
          message: `File extension "${ext}" does not match content type "${file.type}". Please verify the file.`,
        },
      };
    }

    return { valid: true };
  }
}

export const fileValidationService = new FileValidationService();
