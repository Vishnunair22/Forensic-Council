const INTERNAL_PATH_RE = /(?:\/app\/storage\/evidence|[A-Za-z]:\\[^.?!\n\r]{0,120}?storage\\evidence)[^\s,;)]+/gi;
const UUID_FILE_RE = /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(?:png|jpe?g|webp|gif|mp4|mov|avi|wav|mp3|m4a|pdf)\b/gi;

/**
 * Add a visual prefix for non-court-defensible findings.
 * Stubs and low-confidence findings should be visually distinguished.
 */
export function formatFindingTitle(findingType: string, courtDefensible?: boolean): string {
  if (courtDefensible === false) {
    return `⚠ ${findingType} (indicative only)`;
  }
  return findingType;
}

export function cleanFindingText(text: string | null | undefined, maxLen?: number) {
  let cleaned = String(text || "")
    .replace(INTERNAL_PATH_RE, "the submitted file")
    .replace(UUID_FILE_RE, "the submitted file")
    .replace(/\bThe image file\s+the submitted file\s+/gi, "The submitted file ")
    .replace(/\bwas analyzed using\s+Agent\d_[^.]+\.?\s*/gi, "")
    .replace(/\s+/g, " ")
    .trim();

  cleaned = cleaned
    .replace(/\badvanced neural analysis confirms (?:the image's )?authenticity\.?/gi, "the completed neural check did not report a high-confidence manipulation signal.")
    .replace(/\bmatches the expected hash\b/gi, "matched the intake custody hash")
    .replace(/\bmatches the expected content\b/gi, "matches the visible OCR context")
    .replace(/\bempty raw tool results\b/gi, "no usable tool output")
    .replace(/\black of results\b/gi, "limited tool output");

  if (!maxLen || cleaned.length <= maxLen) return cleaned;
  const clipped = cleaned.slice(0, maxLen);
  const lastSpace = clipped.lastIndexOf(" ");
  return `${lastSpace > 40 ? clipped.slice(0, lastSpace) : clipped}...`;
}
