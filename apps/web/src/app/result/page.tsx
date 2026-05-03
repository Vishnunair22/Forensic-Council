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

  if (!rs.sessionId) {
    return <ResultLayout />;
  }

  return null;
}
