"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { storage } from "@/lib/storage";
import { STORAGE_KEYS } from "@/lib/storageKeys";

export function ResultClientRedirect() {
  const router = useRouter();

  useEffect(() => {
    const sessionId = storage.getItem(STORAGE_KEYS.SESSION_ID);
    if (sessionId) {
      router.replace(`/result/${sessionId}`);
    } else {
      router.replace("/");
    }
  }, [router]);

  return null;
}
