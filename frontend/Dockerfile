# syntax=docker/dockerfile:1.7
# ============================================================================
# Frontend — Multi-Stage Build (development + production)
# ============================================================================
# Targets:
#   development  — hot-reload dev server  (used by: make dev)
#   runner       — optimised production   (used by: make up / make prod)
#
# Build for development:
#   docker build --target development -t forensic-frontend:dev .
# Build for production (default):
#   docker build -t forensic-frontend:latest .
# ============================================================================

# ── Stage 0: Base — shared dependency installation ───────────────────────────
FROM node:22-alpine AS base

WORKDIR /app

COPY package.json package-lock.json ./

# Use npm ci with legacy-peer-deps for reproducible builds.
# React 19 introduces stricter peer dependency enforcement. Several transitive
# dependencies (e.g. older Radix UI packages, lightswind) have not yet published
# React 19-compatible peer ranges. Once upstream releases resolve these conflicts,
# remove --legacy-peer-deps. Tracked: check `npm ls react react-dom` periodically.
RUN --mount=type=cache,target=/root/.npm \
    npm ci --legacy-peer-deps --prefer-offline --no-audit --no-fund && \
    npm cache clean --force && \
    npm cache clean --force

# ── Stage 1: Development — hot-reload server ─────────────────────────────────
FROM base AS development

COPY . .

ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=development

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
  CMD wget -qO- http://localhost:3000/ > /dev/null || exit 1

CMD ["npm", "run", "dev"]

# ── Stage 2: Builder — production build ──────────────────────────────────────
FROM base AS builder

# Copy source
COPY . .

# Build-time variables baked into the JS bundle
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_DEMO_PASSWORD
# INTERNAL_API_URL must be a build-time ARG so next.config.ts rewrites() can
# resolve it during `next build` — it is NOT available as a runtime-only env var
# because rewrites are serialised into routes-manifest.json at build time.
ARG INTERNAL_API_URL=http://forensic_api:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_DEMO_PASSWORD=${NEXT_PUBLIC_DEMO_PASSWORD}
ENV INTERNAL_API_URL=${INTERNAL_API_URL}
ENV NEXT_TELEMETRY_DISABLED=1

# BuildKit cache mount preserves Next.js compiler cache between rebuilds
# → near-instant recompilation when only source files change
RUN --mount=type=cache,target=/app/.next/cache \
    npm run build

# ── Stage 3: Runner — minimal production image ───────────────────────────────
FROM node:22-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
# Standalone Next.js server must bind to 0.0.0.0 so Docker health-checks
# and external traffic can reach it. Without this it defaults to localhost only.
ENV HOSTNAME=0.0.0.0
ENV PORT=3000

# Create a dedicated non-root user for security — running as root in production
# containers is a critical vulnerability that grants full container filesystem
# access on any RCE exploit.
RUN addgroup --system --gid 1001 nodejs \
 && adduser  --system --uid  1001 nextjs

# Copy standalone output (Next.js built-in server)
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

# Switch to non-root user before the process starts
USER nextjs

# Health-check: use the root path (always served by Next.js standalone).
# Previously used /api/health which is not a defined route and would always fail.
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 \
  CMD wget -qO- http://localhost:3000/ > /dev/null || exit 1

EXPOSE 3000

CMD ["node", "server.js"]
