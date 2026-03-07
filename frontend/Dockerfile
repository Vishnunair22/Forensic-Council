# syntax=docker/dockerfile:1.7
# ============================================================================
# Frontend — Optimised Two-Stage Build
# ============================================================================

# ── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /app

# Copy lock files first for better layer caching
COPY package.json package-lock.json ./

# BuildKit cache mount keeps npm's package cache between builds → much faster
RUN --mount=type=cache,target=/root/.npm \
    npm ci --prefer-offline --no-audit --no-fund

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

# ── Stage 2: Runner ──────────────────────────────────────────────────────────
FROM node:22-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Copy standalone output (Next.js built-in server)
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=5 \
  CMD node -e "require('http').get('http://127.0.0.1:3000', r => process.exit(r.statusCode === 200 ? 0 : 1)).on('error', () => process.exit(1))"

EXPOSE 3000

CMD ["node", "server.js"]
