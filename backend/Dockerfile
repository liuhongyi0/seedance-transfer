# ─────────────────────────────────────────────
# Seedance Wizard Backend — 海外版 Docker 构建
# 多阶段构建，DEPLOYMENT_REGION 通过 ARG 传入
# ─────────────────────────────────────────────

FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --production=false
COPY tsconfig.json ./
COPY src/ ./src/
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ARG DEPLOYMENT_REGION=cn
ENV NODE_ENV=production
ENV DEPLOYMENT_REGION=${DEPLOYMENT_REGION}

COPY package.json package-lock.json* ./
RUN npm ci --production && npm cache clean --force
COPY --from=builder /app/dist ./dist
COPY config/ ./config/
COPY ../contract/db-schema.sql ./contract/db-schema.sql

EXPOSE 3000
CMD ["node", "dist/server.js"]
