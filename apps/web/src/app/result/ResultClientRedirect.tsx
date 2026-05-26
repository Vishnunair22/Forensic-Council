"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { storage } from "@/lib/storage";
import { STORAGE_KEYS } from "@/lib/storageKeys";
import { toast } from "@/hooks/use-toast";

export function ResultClientRedirect() {
  const router = useRouter();

  useEffect(() => {
    const sessionId = storage.getItem(STORAGE_KEYS.SESSION_ID);
    if (sessionId) {
      router.replace(`/result/${sessionId}`);
    } else {
      toast.destructive({
        title: "No active session",
        description: "Start a new investigation to view results.",
      });
      router.replace("/");
    }
  }, [router]);

  return null;
}
