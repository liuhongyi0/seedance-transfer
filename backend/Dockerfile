# ─────────────────────────────────────────────
# Seedance Wizard Backend — Docker 构建
# 构建上下文: 项目根目录
# ─────────────────────────────────────────────

FROM node:20-alpine AS builder
WORKDIR /app
COPY backend/package.json backend/package-lock.json* ./
RUN npm ci --production=false
COPY backend/tsconfig.json ./
COPY backend/src/ ./src/
# db-schema.sql 在构建时复制到 dist/（跳过 package.json 里的 cp）
RUN npx tsc

FROM node:20-alpine AS runner
WORKDIR /app
ARG DEPLOYMENT_REGION=intl
ENV NODE_ENV=production
ENV DEPLOYMENT_REGION=${DEPLOYMENT_REGION}

COPY backend/package.json backend/package-lock.json* ./
RUN npm ci --production && npm cache clean --force
COPY --from=builder /app/dist ./dist
COPY backend/config/ ./config/
COPY contract/db-schema.sql ./dist/db-schema.sql
COPY contract/db-schema.sql ./dist/db/db-schema.sql

EXPOSE 3000
CMD ["node", "dist/server.js"]
