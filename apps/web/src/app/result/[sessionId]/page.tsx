import { DynamicResultClient } from "@/components/pages/DynamicResultClient";

export const dynamic = "force-dynamic";

interface ResultPageProps {
  params: Promise<{ sessionId: string }>;
}

export default async function DynamicResultPage({ params }: ResultPageProps) {
  const { sessionId } = await params;
  return <DynamicResultClient sessionId={sessionId} />;
}