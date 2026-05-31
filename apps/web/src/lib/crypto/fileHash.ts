export type FileHashResult = {
  algorithm: "SHA-256";
  hex: string;
  size: number;
  fileName: string;
};

export async function computeFileSha256(file: File): Promise<FileHashResult> {
  if (!globalThis.crypto?.subtle) {
    throw new Error("Browser Web Crypto API is unavailable.");
  }

  const buffer = await file.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  const hex = Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  if (!/^[a-f0-9]{64}$/.test(hex)) {
    throw new Error("Invalid SHA-256 digest generated.");
  }

  return {
    algorithm: "SHA-256",
    hex,
    size: file.size,
    fileName: file.name,
  };
}
