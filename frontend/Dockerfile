FROM node:22-alpine AS base

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

COPY . .

FROM base AS builder
# Bake NEXT_PUBLIC_* vars at build time (they cannot be set at runtime)
ARG NEXT_PUBLIC_EXAM_API_URL=http://localhost:8001/api/v1
ENV NEXT_PUBLIC_EXAM_API_URL=$NEXT_PUBLIC_EXAM_API_URL
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3001
CMD ["node", "server.js"]
