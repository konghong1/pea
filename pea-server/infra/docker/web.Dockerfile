# Web (React + Vite) 镜像 — 多阶段构建, nginx 提供静态资源并反向代理 BFF
FROM node:20-alpine AS build

# 构建参数: 默认用国内 npm 镜像 (海外部署可覆盖:
#   docker compose build --build-arg NPM_REGISTRY=https://registry.npmjs.org/)
ARG NPM_REGISTRY=https://registry.npmmirror.com
ENV npm_config_registry=$NPM_REGISTRY

WORKDIR /app
COPY web/package*.json ./
RUN npm install
COPY web/ ./
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY infra/docker/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
