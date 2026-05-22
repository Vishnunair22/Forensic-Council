import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { ResultClientRedirect } from "./ResultClientRedirect";
import { STORAGE_KEYS } from "@/lib/storageKeys";

export default async function ResultPage() {
  const cookieStore = await cookies();
  const sessionId = cookieStore.get(STORAGE_KEYS.SESSION_ID)?.value;

  if (sessionId) {
    redirect(`/result/${sessionId}`);
  }

  // If no cookie, fall back to client component which reads localStorage
  return <ResultClientRedirect />;
}
