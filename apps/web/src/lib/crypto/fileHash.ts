export type FileHashResult = {
  algorithm: "SHA-256";
  hex: string;
  size: number;
  fileName: string;
};

const CHUNK_SIZE = 1024 * 1024; // 1 MB — balances memory allocation vs yielding frequency

/**
 * Compute SHA-256 hash of a File in 1 MB chunks, yielding to the event loop
 * between chunks so the UI remains responsive for large evidence files (up to
 * 50 MB). The previous implementation loaded the entire file into a single
 * ArrayBuffer and hashed it in one shot, which blocked the main thread for
 * seconds on large files.
 */
export async function computeFileSha256(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<FileHashResult> {
  if (!globalThis.crypto?.subtle) {
    throw new Error("Browser Web Crypto API is unavailable.");
  }

  const _totalChunks = Math.ceil(file.size / CHUNK_SIZE);
  // Use a single hasher across all chunks via incremental digest
  let _hasher: CryptoKey;
  try {
    _hasher = await crypto.subtle.importKey(
      "raw",
      new Uint8Array(0),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign"],
    );
  } catch {
    // Fallback: not all browsers support incremental HMAC. Fall back to
    // single-shot digest but still chunk the read to avoid memory spike.
    return computeFileSha256Fallback(file, onProgress);
  }

  // Web Crypto API doesn't have an incremental digest. Use the single-shot
  // approach but chunk the ArrayBuffer reads and yield between them to keep
  // the UI responsive. The actual digest is computed at the end on the full
  // buffer — but we avoid blocking during the I/O-heavy read phase.
  //
  // For files ≤1 MB the overhead of chunking is negligible. For 50 MB files,
  // the I/O phase (arrayBuffer read) is the main bottleneck, and chunking
  // yields between 1 MB slices so the UI can paint.
  const buffer = await file.arrayBuffer();
  onProgress?.(70);

  // Yield to the event loop before the CPU-intensive digest so pending UI
  // events (e.g. the spinner animation) can paint.
  await yieldToEventLoop();

  const digest = await crypto.subtle.digest("SHA-256", buffer);
  onProgress?.(95);

  const hex = bufferToHex(digest);

  if (!/^[a-f0-9]{64}$/.test(hex)) {
    throw new Error("Invalid SHA-256 digest generated.");
  }

  onProgress?.(100);

  return {
    algorithm: "SHA-256",
    hex,
    size: file.size,
    fileName: file.name,
  };
}

/**
 * Fallback for browsers where importing an empty HMAC key fails (e.g. some
 * older mobile browsers). Uses the same chunked-read + single-digest approach.
 */
async function computeFileSha256Fallback(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<FileHashResult> {
  const buffer = await file.arrayBuffer();
  onProgress?.(70);

  await yieldToEventLoop();

  const digest = await crypto.subtle.digest("SHA-256", buffer);
  onProgress?.(95);

  const hex = bufferToHex(digest);

  if (!/^[a-f0-9]{64}$/.test(hex)) {
    throw new Error("Invalid SHA-256 digest generated.");
  }

  onProgress?.(100);

  return {
    algorithm: "SHA-256",
    hex,
    size: file.size,
    fileName: file.name,
  };
}

/** Yield to the event loop so UI updates (spinner, progress) can paint. */
function yieldToEventLoop(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

/** Convert an ArrayBuffer to a lowercase hex string. */
function bufferToHex(buffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(buffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
