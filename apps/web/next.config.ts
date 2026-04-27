import type { NextConfig } from "next";
import path from "path";

/**
 * Chrome DevTools maps stack frames using source-map `sources` paths. Bare
 * Windows paths with spaces can be rejected as "illegal path"; keep dev-source
 * paths virtual and URL-encoded so Chrome does not treat them as host files.
 */
function devtoolModulePathForChrome(resourcePath: string): string {
  if (!resourcePath) return "webpack://forensic-council/unknown";
  // Strip webpack loader prefixes (e.g. 'next-swc-loader!src/api.ts' -> 'src/api.ts')
  const cleanPath = (resourcePath.split("!").pop() || resourcePath).replace(/\\/g, "/");
  const cwd = process.cwd().replace(/\\/g, "/");
  const withoutCwd = cleanPath.startsWith(`${cwd}/`)
    ? cleanPath.slice(cwd.length + 1)
    : cleanPath.replace(/^[A-Za-z]:\//, "");

  const encodedPath = withoutCwd
    .split("/")
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join("/");

  return `webpack://forensic-council/${encodedPath || "unknown"}`;
}

const nextConfig: NextConfig = {
  // ── Output ────────────────────────────────────────────────────────────────
  // Standalone mode: copies only required files into .next/standalone,
  // reducing the production Docker image from ~1 GB to ~150 MB.
  output: "standalone",

  // ── Compression ──────────────────────────────────────────────────────────
  // Disabled: Caddy handles compression via `encode zstd gzip` in Caddyfile.
  // Enabling both causes double-compression (wasted CPU, slightly larger output).
  compress: false,

  // ── TypeScript & ESLint ───────────────────────────────────────────────
  // Note: transpilePackages is no longer needed for class-variance-authority in Next 15.


  // ── Turbopack (Next.js 15 default build engine) ───────────────────────────
  // Declaring an explicit Turbopack config suppresses the
  // "webpack config + no turbopack config" warning when Turbopack is enabled.
  // The webpack config below is retained for the default Next.js dev server on
  // Windows Docker bind mounts.
  turbopack: {
    resolveExtensions: [".tsx", ".ts", ".jsx", ".js", ".json"],
    // Removed redundant class-variance-authority alias
  },

  // ── Bundle optimisation ───────────────────────────────────────────────────
  experimental: {
    // Tree-shakes these packages at the module level so only imported icons
    // and motion components are bundled — cuts ~400 KB from the initial JS.
    optimizePackageImports: [
      "lucide-react",
      "framer-motion",
      "@radix-ui/react-dialog",
    ],
    // Inline small CSS into JS bundle (saves one HTTP round-trip on first load).
    // Disabled in dev mode to improve stability.
    optimizeCss: false,
    // Performance optimizations for large builds
    webpackBuildWorker: true,
    parallelServerBuildTraces: true,
  },

  // ── Dev-mode file watcher (Windows + Docker fallback) ────────────────────
  // On Windows bind mounts, inotify events are not forwarded into the container
  // reliably, so polling restores HMR. The custom source-map template also
  // avoids Chrome "illegal path" errors for host paths with spaces.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  webpack: (config: any, { dev }: { dev: boolean }) => {
    // Removed redundant class-variance-authority alias

    if (dev) {
      config.watchOptions = {
        poll: 500, // Reduced from 800ms to 500ms for faster HMR
        aggregateTimeout: 300,
      };
      // Use relative, URL-encoded paths for source maps to avoid "illegal path"
      // errors with Windows absolute paths containing spaces.
      config.output = {
        ...config.output,
        devtoolModuleFilenameTemplate: (info: { resourcePath: string }) =>
          devtoolModulePathForChrome(info.resourcePath),
      };
    }
    return config;
  },

  // ── Image optimisation ────────────────────────────────────────────────────
  images: {
    // Next.js built-in WebP/AVIF conversion for any <Image> components.
    formats: ["image/avif", "image/webp"],
    // Immutable cache: 1 year. Images are content-hashed so this is safe.
    minimumCacheTTL: 31_536_000,
  },

  // ── Backend API Proxy ─────────────────────────────────────────────────────
  // /api/v1/* is handled by the App Router proxy route in
  // src/app/api/v1/[...path]/route.ts so requests can retry across backend
  // targets instead of relying on a single static rewrite destination.
  async rewrites() {
    return [];
  },

  // ── HTTP response headers ─────────────────────────────────────────────────
  async headers() {
    return [
      {
        source: "/",
        headers: [
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
        ],
      },
      {
        // HTML pages — never cache: browser must revalidate on every visit.
        // Next.js 15 defaults to s-maxage=31536000 for static pages which
        // causes stale HTML to persist in the browser cache across deploys.
        source: "/(evidence|result|session-expired)",
        headers: [
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
        ],
      },
      {
        // Fonts: content-hashed, safe to cache long-term.
        source: "/fonts/:path*",
        headers: [
          { key: "Cache-Control", value: "public, max-age=31536000, immutable" },
        ],
      },
      {
        // Static public assets: moderate cache with revalidation.
        source: "/(favicon.ico|robots.txt|sitemap.xml)",
        headers: [
          { key: "Cache-Control", value: "public, max-age=86400, must-revalidate" },
        ],
      },
      {
        // API routes: defense-in-depth security headers
        source: "/api/:path*",
        headers: [
          { key: "Cache-Control", value: "no-store, no-cache, must-revalidate, proxy-revalidate" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-XSS-Protection", value: "0" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
      {
        // Global security headers for all page routes
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-XSS-Protection", value: "0" },
          {
            key: "Content-Security-Policy",
            // In dev, the browser may be on localhost:3000 (Next.js direct) while
            // WebSocket connects to ws://localhost:80 (Caddy). Different ports = different
            // origin, which 'self' alone doesn't cover — add explicit ws://localhost so
            // the browser allows the upgrade regardless of which port serves the page.
            value: process.env.NODE_ENV === "production"
              ? "default-src 'self'; script-src 'self' 'unsafe-eval' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self'; font-src 'self' data:; frame-ancestors 'none'; form-action 'self';"
              : "default-src 'self'; script-src 'self' 'unsafe-eval' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self' ws://localhost wss://localhost ws://localhost:3000 wss://localhost:3000; font-src 'self' data:; frame-ancestors 'none'; form-action 'self';",
          },
          ...(process.env.NODE_ENV === "production" ? [
            { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
          ] : []),
        ],
      },
    ];
  },
};

export default nextConfig;
