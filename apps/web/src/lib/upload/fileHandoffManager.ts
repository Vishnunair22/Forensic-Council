import { __pendingFileStore } from "@/lib/pendingFileStore";
import { sessionOnlyStorage } from "@/lib/storage";
import { STORAGE_KEYS } from "@/lib/storageKeys";
import { clearInvestigationPersistence } from "@/lib/investigationStorage";
import {
  savePendingEvidenceFile,
  loadPendingEvidenceFile,
  clearPendingEvidenceFile,
} from "@/lib/pendingFilePersistence";

export class FileHandoffManager {
  async prepareUpload(file: File, options?: { clientSha256?: string | null }): Promise<void> {
    __pendingFileStore.file = file;
    clearInvestigationPersistence();

    sessionOnlyStorage.setItem(STORAGE_KEYS.AUTO_START, "true");
    sessionOnlyStorage.setItem(STORAGE_KEYS.FC_SHOW_LOADING, "true");
    sessionOnlyStorage.setItem(STORAGE_KEYS.FC_HARD_REFRESH_GUARD, String(Date.now()));
    sessionOnlyStorage.setItem(
      STORAGE_KEYS.FC_PENDING_FILE_META,
      JSON.stringify({
        name: file.name,
        type: file.type,
        size: file.size,
        updatedAt: Date.now(),
        clientSha256: options?.clientSha256 ?? null,
      }),
      true,
    );

    try {
      await savePendingEvidenceFile(file);
    } catch {
      console.warn("[FileHandoffManager] could not persist pending file to IndexedDB");
    }
  }

  async recoverFile(): Promise<File | null> {
    let pending = __pendingFileStore.file;
    if (!pending && sessionOnlyStorage.getItem(STORAGE_KEYS.AUTO_START) === "true") {
      pending = await loadPendingEvidenceFile().catch(() => null);
      if (pending) __pendingFileStore.file = pending;
    }
    return pending;
  }

  cleanup(): void {
    __pendingFileStore.file = null;
    clearInvestigationPersistence();
    clearPendingEvidenceFile().catch(() => {});
    sessionOnlyStorage.removeItem(STORAGE_KEYS.AUTO_START);
    sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
    sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_HANDOFF_FIRED);
    sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_PENDING_FILE_META);
    sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_HARD_REFRESH_GUARD);
    sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_LOADING_TEXT);
    sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_LOADING_DISPATCHED);
    sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_ARBITER_TRANSITIONING);
    sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_REPORT_READY);
  }

  getFileMeta(): { name: string; type: string; size: number } | null {
    const raw = sessionOnlyStorage.getItem(STORAGE_KEYS.FC_PENDING_FILE_META, true, null);
    if (raw && typeof raw === "object" && "name" in raw) {
      return raw as { name: string; type: string; size: number };
    }
    return null;
  }

  getPendingClientSha256(): string | null {
    const meta = this.getFileMeta() as ({ clientSha256?: string } | null);
    const hash = meta?.clientSha256 ?? null;
    return hash && /^[a-f0-9]{64}$/i.test(hash) ? hash.toLowerCase() : null;
  }
}

export const fileHandoffManager = new FileHandoffManager();
