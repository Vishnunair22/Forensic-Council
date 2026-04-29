function normalizeBaseUrl(url: string): string {
  return url.replace(/\/+$/, "");
}

export function getBackendBaseUrls(): string[] {
  const internalUrl = process.env.INTERNAL_API_URL;
  const publicUrl = process.env.NEXT_PUBLIC_API_URL;
  const isDocker = Boolean(process.env.RUNNING_IN_DOCKER);
  const isProduction = process.env.NODE_ENV === "production";

  const devCandidates = isDocker
    ? [internalUrl, "http://backend:8000", "http://forensic_api:8000", publicUrl, "http://host.docker.internal:8000"]
    : [internalUrl, publicUrl, "http://localhost:8000", "http://127.0.0.1:8000"];

  const prodCandidates = [
    internalUrl,
    publicUrl,
  ].filter((v): v is string => Boolean(v?.trim()));

  const candidates = isProduction ? prodCandidates : devCandidates;
  const targets = [...new Set(candidates.map(normalizeBaseUrl))];
  return targets;
}


export function backendUrlFor(pathname: string, baseUrl: string): string {
  const cleanPath = pathname.startsWith("/") ? pathname : `/${pathname}`;
  return `${normalizeBaseUrl(baseUrl)}${cleanPath}`;
}
