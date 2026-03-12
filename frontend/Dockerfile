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

# BuildKit cache mount keeps npm's package cache between builds → much faster
RUN --mount=type=cache,target=/root/.npm \
    npm ci --prefer-offline --no-audit --no-fund

# ── Stage 1: Development — hot-reload server ─────────────────────────────────
FROM base AS development

COPY . .

ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=development

EXPOSE 3000

CMD ["npm", "run", "dev"]

# ── Stage 2: Builder — production build ──────────────────────────────────────
FROM base AS builder

# Copy source
COPY . .

# Build-time variables baked into the JS bundle
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_DEMO_PASSWORD
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_DEMO_PASSWORD=${NEXT_PUBLIC_DEMO_PASSWORD}
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

# Health-check: use wget (available in alpine) hitting 0.0.0.0 which is where
# the standalone server listens. Increase start-period to give Next.js time to boot.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
  CMD wget -qO- http://0.0.0.0:3000/ > /dev/null || exit 1

EXPOSE 3000

CMD ["node", "server.js"]
