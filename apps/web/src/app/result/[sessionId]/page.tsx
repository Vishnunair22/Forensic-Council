"use client";

import React from "react";
import { ResultLayout } from "@/components/result/ResultLayout";

interface ResultPageProps {
  params: Promise<{ sessionId: string }>;
}

export default function DynamicResultPage({ params }: ResultPageProps) {
  const { sessionId } = React.use(params);
  return <ResultLayout initialSessionId={sessionId} />;
}
