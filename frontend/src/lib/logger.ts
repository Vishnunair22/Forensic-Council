/**
 * Shared Dev-Only Logger Utility
 *
 * Provides consistent logging pattern across the frontend codebase.
 * All console output is silenced in production builds for security and performance.
 */

const isDev = process.env.NODE_ENV !== "production";

export const logger = {
  log: isDev ? console.log.bind(console) : () => {},
  warn: isDev ? console.warn.bind(console) : () => {},
  error: isDev ? console.error.bind(console) : () => {},
  debug: isDev ? console.debug.bind(console) : () => {},
  info: isDev ? console.info.bind(console) : () => {},
};

/**
 * Log in development mode only
 */
export function devLog(message: string, ...args: unknown[]): void {
  if (isDev) {
    console.log(`[${new Date().toISOString()}] ${message}`, ...args);
  }
}

/**
 * Log errors - always log errors but sanitize in production
 */
export function logError(context: string, error: unknown): void {
  if (isDev) {
    console.error(`[${context}]`, error);
  }
}

/**
 * Performance timing logger for development
 */
export function perfLog(label: string, startTime: number): void {
  if (isDev) {
    const duration = performance.now() - startTime;
    console.log(`[Perf] ${label}: ${duration.toFixed(2)}ms`);
  }
}

export default logger;
