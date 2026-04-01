// Module-scoped store for passing File objects between SPA pages.
// File objects cannot be serialized to sessionStorage/URL, so this is the
// only viable approach. Scoped to the module — not globalThis — to avoid
// polluting the global namespace and colliding with other code.
export const __pendingFileStore: { file: File | null } = { file: null };
