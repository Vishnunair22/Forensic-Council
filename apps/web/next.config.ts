import type { NextConfig } from "next";
import path from "path";

/**
 * Chrome DevTools maps stack frames using source-map `sources` paths. Unescaped
 * spaces (e.g. `D:/Forensic Council/...`) are rejected as "illegal path"; encode
 * each segment except the Windows drive prefix.
 */
function devtoolModulePathForChrome(absoluteResourcePath: string): string {
  if (!absoluteResourcePath) return "";
  const forward = absoluteResourcePath.replace(/\\/g, "/");
  return forward
    .split("/")
    .map((segment) => {
      if (segment === "" || /^[a-zA-Z]:$/.test(segment)) return segment;
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

  // ── TypeScript & ESLint ───────────────────────────────────────────────
  transpilePackages: ["class-variance-authority"],

  // ── Turbopack (Next.js 15 default build engine) ───────────────────────────
  // Turbopack is the default bundler in Next.js 15. Declaring an explicit
  // turbopack config suppresses the "webpack config + no turbopack config"
  // warning. The webpack config below is retained for `next dev --webpack`
  // on Windows Docker bind mounts; it has no effect on Turbopack builds.
  turbopack: {
    resolveExtensions: ['.tsx', '.ts', '.jsx', '.js', '.json'],
    resolveAlias: {
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
    ],
    // Inline small CSS into JS bundle (saves one HTTP round-trip on first load).
    // Disabled in dev mode to improve stability.
    optimizeCss: false,
  },

  // ── Dev-mode file watcher (Windows + Docker fallback) ────────────────────
  // Used only when running `next dev --webpack`. On Windows bind mounts,
  // inotify events are not forwarded into the container so switching to
  // polling restores reliable HMR. No effect on Turbopack builds.
  webpack: (config: Record<string, unknown> & { resolve: { alias: Record<string, string> }; watchOptions?: unknown; output?: Record<string, unknown> }, { dev }: { dev: boolean }) => {
    config.resolve.alias = {
      ...config.resolve.alias,
      'class-variance-authority': path.resolve(process.cwd(), 'node_modules/class-variance-authority'),
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
          { key: "Content-Security-Policy", value: "default-src 'self'; script-src 'self' 'unsafe-eval' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self' ws: wss:; font-src 'self' data:; frame-ancestors 'none'; form-action 'self';" },
          { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
        ],
      },
    ];
  },
};

export default nextConfig;
