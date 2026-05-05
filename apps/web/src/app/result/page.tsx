import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { ResultClientRedirect } from "./ResultClientRedirect";

export default async function ResultPage() {
  const cookieStore = await cookies();
  const sessionId = cookieStore.get("forensic_session_id")?.value;

  if (sessionId) {
    redirect(`/result/${sessionId}`);
  }

  // If no cookie, fall back to client component which reads localStorage
  return <ResultClientRedirect />;
}
