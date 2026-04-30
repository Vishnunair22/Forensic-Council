type PendingFileStore = { file: File | null };

const globalStore = globalThis as typeof globalThis & {
  __fcPendingFileStore?: PendingFileStore;
};

// File objects cannot be serialized to sessionStorage/URL. Keep the selected
// file in a browser-runtime singleton so route chunks and dev HMR instances
// share the same handoff object during the landing -> evidence transition.
export const __pendingFileStore: PendingFileStore =
  globalStore.__fcPendingFileStore ?? { file: null };

globalStore.__fcPendingFileStore = __pendingFileStore;
