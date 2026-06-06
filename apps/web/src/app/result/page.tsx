import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { ResultClientRedirect } from "./ResultClientRedirect";
import { STORAGE_KEYS } from "@/lib/storageKeys";

export default async function ResultPage() {
  // SESSION_ID is stored in localStorage (client only) and sessionStorage,
  // not in a cookie — so this fast-path is currently always a miss.
  // It is kept as a forward-compatible hook in case a server-set cookie is
  // added in future. ResultClientRedirect handles the client-side fallback.
  const cookieStore = await cookies();
  const sessionId = cookieStore.get(STORAGE_KEYS.SESSION_ID)?.value;

  if (sessionId) {
    redirect(`/result/${sessionId}`);
  }

  return <ResultClientRedirect />;
}
