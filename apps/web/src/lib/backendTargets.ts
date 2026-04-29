function normalizeBaseUrl(url: string): string {
  return url.replace(/\/+$/, "");
}

export function getBackendBaseUrls(): string[] {
  // Use process.env directly. In Next.js server-side code (Route Handlers),
  // this is populated from the environment.
  const internalUrl = process.env.INTERNAL_API_URL;
  const publicUrl = process.env.NEXT_PUBLIC_API_URL;

  // In production, only try internal/public URLs to avoid ~6s timeout on fallbacks
  const isProduction = process.env.NODE_ENV === "production";

  const devCandidates = [
    internalUrl,
    "http://backend:8000",          // Docker Compose service name (HIGHEST PRIORITY)
    "http://forensic_api:8000",     // Docker container name
    publicUrl,
    "http://host.docker.internal:8000", // Docker host gateway
    "http://localhost:8000",        // Local development
    "http://127.0.0.1:8000",        // Local fallback
  ];

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
