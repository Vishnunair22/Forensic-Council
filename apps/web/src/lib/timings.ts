/**
 * Central registry of timing constants used across the frontend pipeline.
 * Tune here rather than grep-and-edit across multiple files.
 */

/** Minimum ms to display the arbiter deliberation overlay before advancing */
export const ARBITER_MIN_DISPLAY_MS = 1500;

/** Safety ceiling for the loading overlay — force-dismiss after this long */
export const SAFETY_TIMEOUT_MS = 5_000;

/** Minimum ms to show the loading overlay (prevents flash-of-overlay) */
export const MIN_DISPLAY_MS = 800;

/** Max ms to show the evidence loading overlay before forcing resolution */
export const EVIDENCE_MAX_DISPLAY_MS = 5_000;

/** WS stall detection: emit a stall event if no message is received in this window */
export const STALL_MS = 30_000;

/** Arbiter live-poll interval */
export const ARBITER_POLL_INTERVAL_MS = 1_500;

/** Throttle interval for screen-reader aria-live announcements (ms) */
export const SR_ANNOUNCE_THROTTLE_MS = 2_000;
