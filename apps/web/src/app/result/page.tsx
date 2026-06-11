import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { ResultClientRedirect } from "./ResultClientRedirect";
import { STORAGE_KEYS } from "@/lib/storageKeys";

export default async function ResultPage() {
  // Server-side fast-path: useInvestigation sets a client-side
  // `forensic_session_id` cookie (max-age 3600) when an investigation starts,
  // so a bare /result visit or refresh during an active session redirects
  // straight to /result/<sid> without a client round-trip. After the cookie
  // expires or a reset clears it, ResultClientRedirect handles the
  // localStorage-based client-side fallback (or routes home with a toast).
  const cookieStore = await cookies();
  const sessionId = cookieStore.get(STORAGE_KEYS.SESSION_ID)?.value;

  if (sessionId) {
    redirect(`/result/${sessionId}`);
  }

  return <ResultClientRedirect />;
}
