import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // ── Output ────────────────────────────────────────────────────────────────
  // Standalone mode: copies only required files into .next/standalone,
  // reducing the production Docker image from ~1 GB to ~150 MB.
  output: "standalone",

  // ── Compression ──────────────────────────────────────────────────────────
  // Enables gzip on all responses from the Next.js server.
  // If serving behind Caddy/nginx, set to false — the reverse proxy handles it.
  compress: true,

  // ── TypeScript ────────────────────────────────────────────────────────
  typescript: { ignoreBuildErrors: false },

  // ── ESLint ────────────────────────────────────────────────────────────────
  // ESLint is run separately in CI (npm run lint).
  // Disabling here keeps Docker builds fast and avoids eslint-config-next
  // version skew issues across major Next.js releases.
  eslint: { ignoreDuringBuilds: true },

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

  // ── Dev-mode file watcher (Windows + Docker fix) ─────────────────────────
  // On Windows bind mounts, inotify events are not forwarded into the container
  // so Next.js emits "Unable to add filesystem: <illegal path>" on every
  // hot-reload cycle.  Switching the webpack watcher to polling silences the
  // error and restores reliable HMR without any user-visible slowdown.
  webpack: (config, { dev }) => {
    if (dev) {
      config.watchOptions = {
        poll: 800,
        aggregateTimeout: 300,
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
        // Immutable static assets: JS/CSS chunks are content-hashed by Next.js.
        // Cache forever — no revalidation needed.
        source: "/_next/static/:path*",
        headers: [
          { key: "Cache-Control", value: "public, max-age=31536000, immutable" },
        ],
      },
      {
        // Fonts: also content-hashed, safe to cache long-term.
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
