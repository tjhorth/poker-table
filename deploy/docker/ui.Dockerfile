# The dealer UI, built once and served as static files by nginx.
# Build context is the repo root:
#   docker build -f deploy/docker/ui.Dockerfile .
FROM node:22-alpine AS build
WORKDIR /src/web/dealer
COPY web/dealer/package.json web/dealer/package-lock.json ./
RUN npm ci
COPY web/dealer/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY deploy/docker/nginx-ui.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/web/dealer/dist /usr/share/nginx/html
EXPOSE 80
