import type { NextConfig } from "next";
import path from "path";

/**
 * Chrome DevTools maps stack frames using source-map `sources` paths. Unescaped
 * spaces (e.g. `D:/Forensic Council/...`) are rejected as "illegal path"; encode
 * each segment except the Windows drive prefix.
 */
function devtoolModulePathForChrome(absoluteResourcePath: string): string {
  const forward = absoluteResourcePath.replace(/\\/g, "/");
  return forward
    .split("/")
    .map((segment) => {
      if (segment === "") return segment;
      if (/^[a-zA-Z]:$/.test(segment)) return segment;
      return encodeURIComponent(segment);
    })
    .join("/");
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

  // ── TypeScript ────────────────────────────────────────────────────────
  typescript: { ignoreBuildErrors: false },
  transpilePackages: ["three", "simplex-noise", "class-variance-authority"],

  // ── Turbopack (Next.js 15 default build engine) ───────────────────────────
  // Turbopack is the default bundler in Next.js 15. Declaring an explicit
  // turbopack config suppresses the "webpack config + no turbopack config"
  // warning. The webpack config below is retained for `next dev --webpack`
  // on Windows Docker bind mounts; it has no effect on Turbopack builds.
  turbopack: {
    resolveExtensions: ['.tsx', '.ts', '.jsx', '.js', '.json'],
    resolveAlias: {
      three: path.resolve(process.cwd(), 'node_modules/three'),
      'simplex-noise': path.resolve(process.cwd(), 'node_modules/simplex-noise'),
      'class-variance-authority': path.resolve(process.cwd(), 'node_modules/class-variance-authority'),
    },
  },

  // ── Bundle optimisation ───────────────────────────────────────────────────
  experimental: {
    // Tree-shakes these packages at the module level so only imported icons
    // and motion components are bundled — cuts ~400 KB from the initial JS.
    optimizePackageImports: [
      "lucide-react",
      "framer-motion",
      "@radix-ui/react-dialog",
      "class-variance-authority",
      // "three",
      // "simplex-noise",
    ],
    // Inline small CSS into JS bundle (saves one HTTP round-trip on first load).
    // Disabled in dev mode to improve stability.
    optimizeCss: false,
  },

  // ── Dev-mode file watcher (Windows + Docker fallback) ────────────────────
  // Used only when running `next dev --webpack`. On Windows bind mounts,
  // inotify events are not forwarded into the container so switching to
  // polling restores reliable HMR. No effect on Turbopack builds.
  webpack: (config, { dev, isServer }) => {
    // Force 'three' to resolve to the local node_modules path
    config.resolve.alias = {
      ...config.resolve.alias,
      'three': path.resolve(process.cwd(), 'node_modules/three'),
      'simplex-noise': path.resolve(process.cwd(), 'node_modules/simplex-noise'),
      'class-variance-authority': path.resolve(process.cwd(), 'node_modules/class-variance-authority/dist/index.js'),
    };

    if (dev) {
      config.watchOptions = {
        poll: 800,
        aggregateTimeout: 300,
      };
      // Normalise Windows paths for Chrome source-map workspace: forward slashes
      // plus URL-encoded segments (spaces in folders like "Forensic Council" break
      // DevTools otherwise). Only applies to `next dev --webpack` (not Turbopack).
      config.output = {
        ...config.output,
        devtoolModuleFilenameTemplate: (info: {
          absoluteResourcePath: string;
        }) => devtoolModulePathForChrome(info.absoluteResourcePath),
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
