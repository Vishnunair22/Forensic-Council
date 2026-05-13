"use client";

import React from "react";
import { ResultLayout } from "@/components/result/ResultLayout";

export function DynamicResultClient({ sessionId }: { sessionId: string }) {
  React.useEffect(() => {
    document.body.style.overflow = "";
  }, []);

  return <ResultLayout initialSessionId={sessionId} />;
}