import type { NextConfig } from "next";
import path from "path";
// Turbopack is the default dev engine in Next.js 15. The webpack() override
// and WATCHPACK_POLLING/CHOKIDAR env vars were removed — they are webpack-only.

const nextConfig: NextConfig = {
  // ── Output ────────────────────────────────────────────────────────────────
  // Standalone mode: copies only required files into .next/standalone,
  // reducing the production Docker image from ~1 GB to ~150 MB.
  // Set NEXT_OUTPUT_STANDALONE=0 in .env to disable (default: enabled).
  output: process.env.NEXT_OUTPUT_STANDALONE === "0" ? undefined : "standalone",

  outputFileTracingRoot: path.resolve(__dirname, "../.."),
  outputFileTracingExcludes: {
    "*": [
      "../**/.git/**",
      "../**/.next/**",
      "../**/coverage/**",
      "../**/test-results/**",
      "../**/playwright-report/**",
      "../**/.pytest_cache/**",
      "../**/__pycache__/**",
      "../**/*.zip",
    ],
  },

  // ── External packages (server-side) ─────────────────────────────────────
  // sharp must be declared external to use the native binary for image optimization.
  // Without this, Next.js falls back to slower unoptimized mode.
  serverExternalPackages: ["sharp"],

  // ── Compression ──────────────────────────────────────────────────────────
  // Disabled: Caddy handles compression via `encode zstd gzip` in Caddyfile.
  // Enabling both causes double-compression (wasted CPU, slightly larger output).
  // Local dev without Caddy can enable if needed (RUNNING_IN_DOCKER=1 for Docker compose).
  compress: process.env.RUNNING_IN_DOCKER === "1",

  // ── TypeScript & ESLint ───────────────────────────────────────────────
  // Strict by default. CI runs `npm run type-check` and `npm run lint`
  // separately, so build-time strictness catches local-dev regressions.
  eslint: {
    ignoreDuringBuilds: false,
  },
  typescript: {
    ignoreBuildErrors: false,
  },


  // ── Turbopack (Next.js 15 default build engine) ───────────────────────────
  // Next.js 15 uses Turbopack by default for `next dev`. Declaring an explicit
  // Turbopack config makes that choice unambiguous and suppresses the
  // "no turbopack config found" warning.
  // Dev file-watching in Docker uses Turbopack's own watcher — WATCHPACK_POLLING
  // and CHOKIDAR_USEPOLLING are webpack-only knobs and are not needed.
  turbopack: {
    resolveExtensions: [".tsx", ".ts", ".jsx", ".js", ".json"],
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
    // Performance optimizations for large builds (opt-in via env vars)
    webpackBuildWorker: process.env.NEXT_EXPERIMENTAL_BUILD_WORKER === "1",
    parallelServerBuildTraces: process.env.NEXT_PARALLEL_SERVER_BUILD_TRACES === "1",
  },

  // ── Image optimisation ────────────────────────────────────────────────────
  images: {
    // Next.js built-in WebP/AVIF conversion for any <Image> components.
    formats: ["image/avif", "image/webp"],
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
        // The (.*) suffix ensures /result/[sessionId] and any nested paths match.
        source: "/(evidence|result|session-expired)(.*)",
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
          {
            key: "X-XSS-Protection",
            value: "0"
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
