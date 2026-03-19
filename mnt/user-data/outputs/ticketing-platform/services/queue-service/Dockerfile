# Dockerfile — shared template for all Node.js microservices
# Copy this into each service directory and adjust COPY paths if needed

FROM node:20-alpine AS builder
WORKDIR /app

# Install deps
COPY package*.json ./
RUN npm ci --omit=dev

# Copy source
COPY tsconfig.json ./
COPY src ./src
COPY ../../../shared ./shared

# Compile TypeScript
RUN npm run build

# ── Runtime image ──────────────────────────────────────────
FROM node:20-alpine AS runtime
WORKDIR /app

COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./

# Non-root user for security
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
USER appuser

EXPOSE 3000
CMD ["node", "dist/index.js"]
