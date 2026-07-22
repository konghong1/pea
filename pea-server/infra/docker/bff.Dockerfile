# BFF (NestJS) 镜像
FROM node:20-alpine AS build
WORKDIR /app
COPY services/bff/package*.json ./
RUN npm install
COPY services/bff/ ./
COPY services/shared ./shared
RUN npm run build

FROM node:20-alpine
WORKDIR /app
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY --from=build /app/shared ./shared
ENV PEA_PORT=4000 NODE_ENV=production
EXPOSE 4000
CMD ["node", "dist/main"]
