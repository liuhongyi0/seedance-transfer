# ─────────────────────────────────────────────
# Seedance Web Portal — Next.js Docker 构建
# ─────────────────────────────────────────────

FROM node:20-alpine AS builder
WORKDIR /app
ARG NEXT_PUBLIC_REGION=cn
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:3000
ENV NEXT_PUBLIC_REGION=${NEXT_PUBLIC_REGION}
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}

COPY package.json package-lock.json* ./
RUN npm ci --production=false
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/package.json ./
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
COPY --from=builder /app/locales ./locales

EXPOSE 3000
CMD ["node", "server.js"]
