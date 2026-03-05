# ============================================================================
# Stage 1: Dependencies - cached separately for faster rebuilds
# ============================================================================
FROM node:20-alpine AS deps

WORKDIR /app

# Copy package locks first for better caching
COPY package.json package-lock.json ./

# Install dependencies - use npm ci for deterministic, faster builds
RUN npm ci --prefer-offline

# ============================================================================
# Stage 2: Builder - builds the Next.js application
# ============================================================================
FROM node:20-alpine AS builder

WORKDIR /app

# Copy deps from previous stage (avoids reinstall)
COPY --from=deps /app/node_modules ./node_modules

# Copy application code
COPY . .

# Build args for Next.js public variables
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_DEMO_PASSWORD=inv123!
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_DEMO_PASSWORD=${NEXT_PUBLIC_DEMO_PASSWORD}

# Disable Next.js telemetry during build
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# ============================================================================
# Stage 3: Runner - production stage with standalone output
# ============================================================================
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Copy standalone output (includes built-in server)
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

# Healthcheck with fixed syntax (added missing closing parenthesis)
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=5 \
  CMD node -e "require('http').get('http://127.0.0.1:3000', r => process.exit(r.statusCode === 200 ? 0 : 1)).on('error', () => process.exit(1))"

EXPOSE 3000

CMD ["node", "server.js"]
