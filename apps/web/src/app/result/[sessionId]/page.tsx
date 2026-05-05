"use client";

import React from "react";
import { ResultLayout } from "@/components/result/ResultLayout";

interface ResultPageProps {
  params: Promise<{ sessionId: string }>;
}

export default function DynamicResultPage({ params }: ResultPageProps) {
  const { sessionId } = React.use(params);
  
  React.useEffect(() => {
    // Failsafe: Ensure body scroll is restored when arriving on results page
    document.body.style.overflow = "";
  }, []);

  return <ResultLayout initialSessionId={sessionId} />;
}
