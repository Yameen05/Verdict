# syntax=docker/dockerfile:1.7

# ---------- builder ----------
FROM node:22-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# ---------- runtime ----------
FROM nginxinc/nginx-unprivileged:1.31.2-alpine AS runtime

# nginx config that serves the SPA and proxies /api to the backend.
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost:8080/ > /dev/null || exit 1
