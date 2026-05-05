"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { ResultLayout } from "@/components/result/ResultLayout";
import { storage } from "@/lib/storage";

export function ResultClientRedirect() {
  const router = useRouter();

  useEffect(() => {
    const sessionId = storage.getItem("forensic_session_id");
    if (sessionId) {
      router.replace(`/result/${sessionId}`);
    } else {
      router.replace("/evidence");
    }
  }, [router]);

  return <ResultLayout />;
}
