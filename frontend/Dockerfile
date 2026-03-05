FROM node:20-alpine AS base

WORKDIR /app

# Copy package locks first
COPY package.json package-lock.json ./

# Install dependencies - use npm ci for deterministic builds
RUN npm install

# Copy application code
COPY . .

# Build the Next.js application for production
ARG NEXT_PUBLIC_API_URL=http://backend:8000
ARG NEXT_PUBLIC_DEMO_PASSWORD=demo123
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_DEMO_PASSWORD=${NEXT_PUBLIC_DEMO_PASSWORD}
RUN npm run build

# Production stage — standalone output
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production

# Copy standalone output (includes built-in server)
COPY --from=base /app/.next/standalone ./
COPY --from=base /app/.next/static ./.next/static
COPY --from=base /app/public ./public

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=5 \
  CMD node -e "require('http').get('http://127.0.0.1:3000', r => {process.stdout.write(''); process.exit(r.statusCode === 200 ? 0 : 1)}).on('error', () => process.exit(1)"

EXPOSE 3000

CMD ["node", "server.js"]
