function normalizeBaseUrl(url: string): string {
  return url.replace(/\/+$/, "");
}

export function getBackendBaseUrls(): string[] {
  // Use process.env directly. In Next.js server-side code (Route Handlers),
  // this is populated from the environment.
  const internalUrl = process.env.INTERNAL_API_URL;

  const candidates = [
    internalUrl,
    "http://backend:8000",          // Docker Compose service name (HIGHEST PRIORITY)
    "http://forensic_api:8000",     // Docker container name
    process.env.NEXT_PUBLIC_API_URL,
    "http://host.docker.internal:8000", // Docker host gateway
    "http://localhost:8000",        // Local development
    "http://127.0.0.1:8000",        // Local fallback
  ].filter((value): value is string => Boolean(value && value.trim()));

  const targets = [...new Set(candidates.map(normalizeBaseUrl))];
  return targets;
}


export function backendUrlFor(pathname: string, baseUrl: string): string {
  const cleanPath = pathname.startsWith("/") ? pathname : `/${pathname}`;
  return `${normalizeBaseUrl(baseUrl)}${cleanPath}`;
}

