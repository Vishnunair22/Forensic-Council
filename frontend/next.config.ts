import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // ── Output ────────────────────────────────────────────────────────────────
  // Standalone mode: copies only required files into .next/standalone,
  // reducing the production Docker image from ~1 GB to ~150 MB.
  output: "standalone",

  // ── Compression ──────────────────────────────────────────────────────────
  // Disabled: Caddy handles compression via `encode zstd gzip` in Caddyfile.
  // Enabling both causes double-compression (wasted CPU, slightly larger output).
  compress: false,

  // ── TypeScript ────────────────────────────────────────────────────────
  typescript: { ignoreBuildErrors: false },

  // ── Turbopack (Next.js 15 default build engine) ───────────────────────────
  // Turbopack is the default bundler in Next.js 15. Declaring an explicit
  // turbopack config suppresses the "webpack config + no turbopack config"
  // warning. The webpack config below is retained for `next dev --webpack`
  // on Windows Docker bind mounts; it has no effect on Turbopack builds.
  turbopack: {},

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
  },

  // ── Dev-mode file watcher (Windows + Docker fallback) ────────────────────
  // Used only when running `next dev --webpack`. On Windows bind mounts,
  // inotify events are not forwarded into the container so switching to
  // polling restores reliable HMR. No effect on Turbopack builds.
  webpack: (config, { dev }) => {
    if (dev) {
      config.watchOptions = {
        poll: 800,
        aggregateTimeout: 300,
      };
      // Normalise Windows backslash paths to forward slashes in source maps.
      // Without this, Chrome receives paths like "d:\Forensic Council\src\..."
      // which it treats as invalid filesystem URIs and logs:
      // "Unable to add filesystem: <illegal path>"
      config.output = {
        ...config.output,
        devtoolModuleFilenameTemplate: (info: { absoluteResourcePath: string }) =>
          info.absoluteResourcePath.replace(/\\/g, "/"),
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

  // ── Backend API Proxy (CORS FIX) ──────────────────────────────────────────
  // All /api/v1/* browser requests are rewritten to the backend by the
  // Next.js server — the browser never makes a cross-origin request, so CORS
  // is entirely bypassed.
  //
  // INTERNAL_API_URL uses the Docker-internal service name (http://forensic_api:8000)
  // so this works both inside Docker and on localhost (falls back gracefully).
  async rewrites() {
    const backendUrl =
      process.env.INTERNAL_API_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      "http://localhost:8000";
    return [
      {
        source: "/api/v1/:path*",
        destination: `${backendUrl}/api/v1/:path*`,
      },
    ];
  },

  // ── HTTP response headers ─────────────────────────────────────────────────
  async headers() {
    return [
      {
        // HTML pages — never cache: browser must revalidate on every visit.
        // Next.js 15 defaults to s-maxage=31536000 for static pages which
        // causes stale HTML to persist in the browser cache across deploys.
        source: "/(|evidence|result|session-expired)",
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
    ];
  },
};

export default nextConfig;
