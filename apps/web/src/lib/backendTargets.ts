function normalizeBaseUrl(url: string): string {
  return url.replace(/\/+$/, "");
}

export function getBackendBaseUrls(): string[] {
  const candidates = [
    process.env.INTERNAL_API_URL,
    "http://backend:8000",
    "http://forensic_api:8000",
    process.env.NEXT_PUBLIC_API_URL,
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://host.docker.internal:8000",
  ].filter((value): value is string => Boolean(value && value.trim()));

  return [...new Set(candidates.map(normalizeBaseUrl))];
}

export function backendUrlFor(pathname: string, baseUrl: string): string {
  const cleanPath = pathname.startsWith("/") ? pathname : `/${pathname}`;
  return `${normalizeBaseUrl(baseUrl)}${cleanPath}`;
}
