import type { TokenResponse } from "./api/types";

type PendingFileStore = {
  file: File | null;
  authPromise: Promise<TokenResponse> | null;
  authError: Error | null;
};

const globalStore = globalThis as typeof globalThis & {
  __fcPendingFileStore?: PendingFileStore;
};

export const __pendingFileStore: PendingFileStore =
  globalStore.__fcPendingFileStore ?? { file: null, authPromise: null, authError: null };

globalStore.__fcPendingFileStore = __pendingFileStore;
