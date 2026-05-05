"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { ResultLayout } from "@/components/result/ResultLayout";
import { useResult } from "@/hooks/useResult";

export default function ResultPage() {
  const router = useRouter();
  const rs = useResult();

  useEffect(() => {
    if (rs.sessionId) {
      router.replace(`/result/${rs.sessionId}`);
    }
  }, [rs.sessionId, router]);

  // Always render the layout so we don't have a blank frame during redirect
  return <ResultLayout />;
}
