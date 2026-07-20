# Stage 1: build della SPA SvelteKit (statica)
FROM node:22-slim AS build
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Caddy serve la SPA e fa da reverse proxy TLS verso l'API
FROM caddy:2-alpine
COPY deploy/caddy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /src/build /srv/www
